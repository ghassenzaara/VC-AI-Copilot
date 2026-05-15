"""Gemini API Client Wrapper

Provides a clean interface to Google's Gemini 2.5 API with:
- Settings-driven defaults (api key, models, temperature, max tokens)
- Native JSON mode via response_mime_type when available
- Safe response handling (safety blocks, empty candidates)
- Retry only on transient errors (5xx, rate limits, timeouts)
- Lenient markdown-fence / JSON-block extraction
- Real embedding via Gemini's text-embedding model
"""

import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Literal

import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import get_settings


logger = logging.getLogger(__name__)


class GeminiError(Exception):
    """Base exception for Gemini API errors (permanent — no retry)."""
    pass


class TransientGeminiError(GeminiError):
    """Transient Gemini error worth retrying (rate limit, 5xx, timeout)."""
    pass


# Patterns used by _parse_json
_FENCE_RE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
_OBJ_RE = re.compile(r'(\{.*\}|\[.*\])', re.DOTALL)


# Module-level lock to detect attempts to use multiple incompatible API keys
# in one process (google.generativeai.configure is a global). BUG-060.
_configured_key: Optional[str] = None


# Module-level minimum interval between any two Gemini calls in the same
# process — applies across all client instances (BUG-072). Defaults to 0.5s
# (~120 RPM) so back-to-back calls don't trip free-tier limits in tests.
_throttle_lock = threading.Lock()
_last_call_at = 0.0
_min_interval_seconds = 0.5


def set_min_call_interval(seconds: float) -> None:
    """Tune the global Gemini call interval (set 0 to disable throttling)."""
    global _min_interval_seconds
    _min_interval_seconds = max(0.0, float(seconds))


def _throttle_before_call() -> None:
    """Sleep just long enough to honor the min-interval between calls."""
    global _last_call_at
    if _min_interval_seconds <= 0:
        return
    with _throttle_lock:
        elapsed = time.time() - _last_call_at
        if elapsed < _min_interval_seconds:
            time.sleep(_min_interval_seconds - elapsed)
        _last_call_at = time.time()


class GeminiClient:
    """Wrapper for Google Gemini API.

    Reads defaults from `src.config.Settings`. Supports both Flash (cheap, fast)
    and Pro (slower, better) models via the `model` arg in the constructor.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Literal["flash", "pro"] = "flash",
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None,
    ):
        """Initialize Gemini client.

        Args:
            api_key: Gemini API key. Defaults to `Settings.gemini_api_key`.
            model: "flash" or "pro". Resolves to `Settings.gemini_model` or
                `Settings.gemini_pro_model`.
            default_temperature: Defaults to `Settings.gemini_temperature`.
            default_max_tokens: Defaults to `Settings.gemini_max_tokens`.
        """
        settings = get_settings()

        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY not found in settings or constructor")

        # BUG-060: google.generativeai.configure is module-global. Two clients
        # with different keys would silently overwrite each other.
        global _configured_key
        if _configured_key and _configured_key != self.api_key:
            raise GeminiError(
                "GeminiClient: cannot use a different API key in the same process "
                "(google.generativeai uses module-global configuration). "
                "Reuse the existing client or migrate to google-genai SDK."
            )
        genai.configure(api_key=self.api_key)
        _configured_key = self.api_key

        # Resolve model name from settings
        self.model_name = settings.gemini_model if model == "flash" else settings.gemini_pro_model
        self.model = genai.GenerativeModel(self.model_name)

        self.default_temperature = (
            default_temperature if default_temperature is not None else settings.gemini_temperature
        )
        self.default_max_tokens = (
            default_max_tokens if default_max_tokens is not None else settings.gemini_max_tokens
        )

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"Initialized Gemini client with model: {self.model_name}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TransientGeminiError),
        reraise=True,
    )
    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Generate text from prompt with automatic retry on transient errors only.

        Args:
            prompt: Input prompt.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            json_mode: If True, request JSON output (native mime type) and append
                a belt-and-braces instruction to the prompt.

        Returns:
            Generated text (stripped).

        Raises:
            TransientGeminiError: Transient failure (retried up to 3 times).
            GeminiError: Permanent failure (no retry).
        """
        config_kwargs: Dict[str, Any] = {
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_output_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
        }
        if json_mode:
            # BUG-012: Use Gemini's native JSON mode where available.
            config_kwargs["response_mime_type"] = "application/json"
            prompt = (
                f"{prompt}\n\n"
                "IMPORTANT: Return ONLY valid JSON, no markdown fences or explanations."
            )

        config = GenerationConfig(**config_kwargs)
        self.logger.debug(f"Generating with {self.model_name} (temp={config.temperature})")

        _throttle_before_call()  # BUG-072: honor global min-interval
        try:
            response = self.model.generate_content(prompt, generation_config=config)
        except Exception as e:
            # Classify the failure as transient vs. permanent.
            msg = str(e).lower()
            transient_markers = ("rate limit", "429", "503", "504", "deadline", "timeout", "unavailable")
            if any(m in msg for m in transient_markers):
                self.logger.warning(f"Transient Gemini error (will retry): {e}")
                raise TransientGeminiError(str(e)) from e
            self.logger.error(f"Permanent Gemini error: {e}")
            raise GeminiError(str(e)) from e

        # BUG-013: response.text raises on safety blocks / multi-candidate responses.
        text = self._extract_text_safely(response)
        if not text:
            raise GeminiError("Empty response from Gemini API (possibly safety-blocked)")
        self.logger.debug(f"Generated {len(text)} characters")
        return text

    @staticmethod
    def _extract_text_safely(response: Any) -> str:
        """Extract text without triggering `response.text`'s strict accessors."""
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            feedback = getattr(response, "prompt_feedback", None)
            logger.warning(f"No candidates returned. prompt_feedback={feedback}")
            return ""

        candidate = candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        # finish_reason 1 == STOP (normal). Anything else is suspicious.
        finish_name = getattr(finish_reason, "name", str(finish_reason)) if finish_reason else "UNKNOWN"
        if finish_name not in ("STOP", "MAX_TOKENS", "1", "2"):
            logger.warning(f"Generation stopped with reason: {finish_name}")
            # MAX_TOKENS is OK — output may be truncated but still parseable.
            # SAFETY / RECITATION / OTHER are not OK.
            if "SAFETY" in finish_name or "RECITATION" in finish_name:
                return ""

        parts = getattr(getattr(candidate, "content", None), "parts", []) or []
        text = "".join(getattr(p, "text", "") or "" for p in parts)
        return text.strip()

    def generate_json(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retry_on_parse_error: bool = True,
    ) -> Dict[str, Any]:
        """Generate and parse a JSON response.

        Strips markdown fences (lenient), retries once on parse failure with a
        stricter instruction.
        """
        text = self.generate(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )

        try:
            return self._parse_json(text)
        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON parse failed on first attempt: {e}")
            if not retry_on_parse_error:
                raise GeminiError(f"Invalid JSON response: {e}") from e

            self.logger.info("Retrying with stricter JSON instruction")
            strict_prompt = (
                f"{prompt}\n\n"
                "Your previous response was not valid JSON. Return ONLY a valid JSON "
                "object with no markdown, no explanations, no code fences. "
                "Start with {{ and end with }}."
            )
            text = self.generate(
                prompt=strict_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            try:
                return self._parse_json(text)
            except json.JSONDecodeError as e2:
                self.logger.error(f"JSON parse failed on retry: {e2}")
                self.logger.error(f"Response text: {text[:500]}")
                raise GeminiError(f"Invalid JSON after retry: {e2}") from e2

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Lenient JSON extraction: strip fences, find first {...} or [...] block, parse."""
        text = (text or "").strip()
        if not text:
            raise json.JSONDecodeError("Empty text", "", 0)

        # BUG-014: lenient — accept preamble/trailing text around the fence.
        fence_match = _FENCE_RE.search(text)
        if fence_match:
            candidate = fence_match.group(1).strip()
            self.logger.debug("Stripped markdown code fences")
            return json.loads(candidate)

        # Try parsing the whole thing first (native JSON mode case).
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fallback: extract first JSON object/array block.
        obj_match = _OBJ_RE.search(text)
        if obj_match:
            return json.loads(obj_match.group(1))

        # Nothing matched — let the caller see the underlying error.
        return json.loads(text)

    def embed_content(
        self,
        text: str,
        output_dimensionality: int = 1536,
        task_type: str = "SEMANTIC_SIMILARITY",
    ) -> List[float]:
        """Generate a real embedding via Gemini's text-embedding model."""
        _throttle_before_call()
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type=task_type,
                output_dimensionality=output_dimensionality,
            )
            embedding = result.get("embedding") if isinstance(result, dict) else result["embedding"]
            if not embedding:
                raise GeminiError("Empty embedding returned from Gemini API")
            return list(embedding)
        except Exception as e:
            self.logger.error(f"Embedding generation failed: {e}")
            raise GeminiError(f"Embedding generation failed: {e}") from e

    def count_tokens(self, text: str) -> int:
        """Return real token count (raises on failure — see estimate_tokens for fallback)."""
        result = self.model.count_tokens(text)
        return result.total_tokens

    def estimate_tokens(self, text: str) -> int:
        """Cheap heuristic: ~4 chars per token. Use when an API call isn't desirable."""
        return max(1, len(text) // 4)

    def switch_model(self, model: Literal["flash", "pro"]) -> None:
        """Switch the underlying model. Reads from current settings."""
        settings = get_settings()
        old_model = self.model_name
        self.model_name = settings.gemini_model if model == "flash" else settings.gemini_pro_model
        self.model = genai.GenerativeModel(self.model_name)
        self.logger.info(f"Switched model: {old_model} -> {self.model_name}")
