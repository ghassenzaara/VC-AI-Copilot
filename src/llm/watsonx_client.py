"""WatsonX API Client Wrapper

Provides a clean interface to IBM WatsonX foundation models with:
- Settings-driven defaults (api key, project, url, models, temperature, max tokens)
- Two purpose-built methods:
    * extract(prompt)          → Llama 3.3 70B Instruct (complex reasoning)
    * filter_relevance(prompt) → Granite 4.0 H Small    (lightweight filtering)
- IAM token auto-refresh (proactive every ~55 min + on-error reset)
- Native chat-completion API for instruct-tuned models
- Lenient markdown-fence / JSON-block extraction
- Real embeddings via IBM Slate (padded/truncated to requested dim)
- Retry only on transient errors (5xx, rate limits, timeouts, expired tokens)
"""

import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Literal, Optional

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import Embeddings, ModelInference
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import get_settings


logger = logging.getLogger(__name__)


class WatsonXError(Exception):
    """Base exception for WatsonX API errors (permanent — no retry)."""
    pass


class TransientWatsonXError(WatsonXError):
    """Transient WatsonX error worth retrying (rate limit, 5xx, timeout, expired token)."""
    pass


_FENCE_RE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
_OBJ_RE = re.compile(r'(\{.*\}|\[.*\])', re.DOTALL)


# Module-level minimum interval between any two WatsonX calls in the same
# process — applies across all client instances. Default 0.2s (~300 RPM).
_throttle_lock = threading.Lock()
_last_call_at = 0.0
_min_interval_seconds = 0.2


# IBM Cloud IAM tokens expire after 1 hour. Refresh proactively at 55 minutes
# to avoid in-flight expiries when a long batch crosses the boundary.
_TOKEN_REFRESH_AFTER_SECONDS = 55 * 60


def set_min_call_interval(seconds: float) -> None:
    """Tune the global WatsonX call interval (set 0 to disable throttling)."""
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


class WatsonXClient:
    """Wrapper for IBM WatsonX foundation models.

    Holds lazily-built model handles for two roles:
        * "pro"   — Llama 3.3 70B Instruct, used by extract()
        * "flash" — Granite 4.0 H Small, used by filter_relevance()

    The constructor accepts `model="flash"|"pro"` which selects the default
    model used by `generate()` / `generate_json()`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        url: Optional[str] = None,
        model: Literal["flash", "pro"] = "flash",
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None,
    ):
        """Initialize WatsonX client.

        Args:
            api_key: IBM Cloud API key. Defaults to `Settings.ibm_api_key`.
            project_id: WatsonX project ID. Defaults to `Settings.ibm_project_id`.
            url: WatsonX endpoint URL. Defaults to `Settings.ibm_url`.
            model: "flash" (granite) or "pro" (llama). Sets the default model
                for `generate()` / `generate_json()`. Methods `extract()` and
                `filter_relevance()` are model-specific and ignore this.
            default_temperature: Defaults to `Settings.watsonx_temperature`.
            default_max_tokens: Defaults to `Settings.watsonx_max_tokens`.
        """
        settings = get_settings()

        self.api_key = api_key or settings.ibm_api_key
        if not self.api_key:
            raise WatsonXError("IBM_API_KEY not found in settings or constructor")

        self.project_id = project_id or settings.ibm_project_id
        if not self.project_id:
            raise WatsonXError("IBM_PROJECT_ID not found in settings or constructor")

        self.url = url or settings.ibm_url

        self._flash_model_id = settings.watsonx_flash_model
        self._pro_model_id = settings.watsonx_pro_model
        self._embedding_model_id = settings.watsonx_embedding_model

        self.default_mode: Literal["flash", "pro"] = model
        self.model_name = self._flash_model_id if model == "flash" else self._pro_model_id

        self.default_temperature = (
            default_temperature if default_temperature is not None else settings.watsonx_temperature
        )
        self.default_max_tokens = (
            default_max_tokens if default_max_tokens is not None else settings.watsonx_max_tokens
        )

        # Lazy-built handles. Rebuilt when IAM credentials are refreshed.
        self._credentials: Optional[Credentials] = None
        self._credentials_built_at: float = 0.0
        self._models: Dict[str, ModelInference] = {}
        self._embeddings: Optional[Embeddings] = None
        self._cred_lock = threading.Lock()

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(
            f"Initialized WatsonX client (default model: {self.model_name}, "
            f"url: {self.url})"
        )

    # ------------------------------------------------------------------
    # Credential and model lifecycle (IAM auto-refresh)
    # ------------------------------------------------------------------

    def _get_credentials(self) -> Credentials:
        """Return a Credentials instance, refreshing if the IAM token is near expiry."""
        with self._cred_lock:
            age = time.time() - self._credentials_built_at
            if self._credentials is None or age > _TOKEN_REFRESH_AFTER_SECONDS:
                if self._credentials is not None:
                    self.logger.info(f"Refreshing IBM IAM credentials (age={age:.0f}s)")
                self._credentials = Credentials(url=self.url, api_key=self.api_key)
                self._credentials_built_at = time.time()
                # Force model handles to rebuild against the fresh credentials.
                self._models.clear()
                self._embeddings = None
            return self._credentials

    def _get_model(self, model_id: str) -> ModelInference:
        """Get (or build) a ModelInference for the given model id."""
        credentials = self._get_credentials()
        model = self._models.get(model_id)
        if model is None:
            self.logger.debug(f"Building ModelInference for {model_id}")
            model = ModelInference(
                model_id=model_id,
                credentials=credentials,
                project_id=self.project_id,
            )
            self._models[model_id] = model
        return model

    def _get_embeddings(self) -> Embeddings:
        """Get (or build) the Embeddings handle."""
        credentials = self._get_credentials()
        if self._embeddings is None:
            self.logger.debug(f"Building Embeddings for {self._embedding_model_id}")
            self._embeddings = Embeddings(
                model_id=self._embedding_model_id,
                credentials=credentials,
                project_id=self.project_id,
            )
        return self._embeddings

    def _force_refresh(self) -> None:
        """Force credentials + all model handles to be rebuilt on next access."""
        self.logger.info("Forcing IBM credentials refresh")
        with self._cred_lock:
            self._credentials = None
            self._credentials_built_at = 0.0
            self._models.clear()
            self._embeddings = None

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        """True if the exception looks like an expired/invalid IAM token."""
        msg = str(exc).lower()
        return any(
            s in msg for s in ("401", "unauthor", "expired", "forbidden", "403")
        ) and ("token" in msg or "iam" in msg or "auth" in msg or "credentials" in msg)

    # ------------------------------------------------------------------
    # Generation primitives
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TransientWatsonXError),
        reraise=True,
    )
    def _generate_on(
        self,
        model_id: str,
        prompt: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        json_mode: bool,
    ) -> str:
        """Chat-completion against a specific model with transient-error retries."""
        if json_mode:
            prompt = (
                f"{prompt}\n\n"
                "IMPORTANT: Return ONLY valid JSON, no markdown fences or explanations."
            )

        temp = temperature if temperature is not None else self.default_temperature
        max_t = max_tokens if max_tokens is not None else self.default_max_tokens

        params: Dict[str, Any] = {
            "temperature": temp,
            "max_tokens": max_t,
        }

        self.logger.debug(f"Generating with {model_id} (temp={temp}, max_tokens={max_t})")
        _throttle_before_call()

        try:
            model = self._get_model(model_id)
            response = model.chat(
                messages=[{"role": "user", "content": prompt}],
                params=params,
            )
        except Exception as e:
            msg = str(e).lower()
            if self._is_auth_error(e):
                self.logger.warning(f"WatsonX auth error — forcing token refresh: {e}")
                self._force_refresh()
                raise TransientWatsonXError(str(e)) from e
            transient_markers = (
                "rate limit", "429", "500", "502", "503", "504",
                "deadline", "timeout", "unavailable", "connection",
            )
            if any(m in msg for m in transient_markers):
                self.logger.warning(f"Transient WatsonX error (will retry): {e}")
                raise TransientWatsonXError(str(e)) from e
            self.logger.error(f"Permanent WatsonX error: {e}")
            raise WatsonXError(str(e)) from e

        text = self._extract_text_safely(response)
        if not text:
            raise WatsonXError("Empty response from WatsonX API")
        self.logger.debug(f"Generated {len(text)} characters")
        return text

    @staticmethod
    def _extract_text_safely(response: Any) -> str:
        """Pull text out of a chat-completion response (OpenAI-compatible shape)."""
        if isinstance(response, str):
            return response.strip()
        if not isinstance(response, dict):
            return ""

        choices = response.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            # Some models return content as a list of parts.
            if isinstance(content, list):
                parts = [
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                ]
                return "".join(parts).strip()

        # Fallback: legacy generate_text shape, in case the SDK falls back.
        results = response.get("results") or []
        if results and isinstance(results[0], dict):
            return (results[0].get("generated_text") or "").strip()

        return ""

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Generate text via the client's default model (set by constructor)."""
        return self._generate_on(
            model_id=self.model_name,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def extract(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Complex-reasoning generation on Llama 3.3 70B Instruct."""
        return self._generate_on(
            model_id=self._pro_model_id,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def filter_relevance(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Lightweight filtering generation on Granite 4.0 H Small."""
        return self._generate_on(
            model_id=self._flash_model_id,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def generate_json(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retry_on_parse_error: bool = True,
    ) -> Dict[str, Any]:
        """Generate and parse a JSON response from the client's default model.

        Strips markdown fences (lenient), retries once on parse failure with
        a stricter instruction.
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
                raise WatsonXError(f"Invalid JSON response: {e}") from e

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
                raise WatsonXError(f"Invalid JSON after retry: {e2}") from e2

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Lenient JSON extraction: strip fences, find first {...} or [...] block, parse."""
        text = (text or "").strip()
        if not text:
            raise json.JSONDecodeError("Empty text", "", 0)

        fence_match = _FENCE_RE.search(text)
        if fence_match:
            candidate = fence_match.group(1).strip()
            self.logger.debug("Stripped markdown code fences")
            return json.loads(candidate)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        obj_match = _OBJ_RE.search(text)
        if obj_match:
            return json.loads(obj_match.group(1))

        return json.loads(text)

    def embed_content(
        self,
        text: str,
        output_dimensionality: int = 768,
        task_type: str = "SEMANTIC_SIMILARITY",
    ) -> List[float]:
        """Generate an embedding via IBM Granite multilingual.

        `granite-embedding-278m-multilingual` natively outputs 768 dims, which
        matches the pgvector column size. `output_dimensionality` is kept as a
        parameter so callers can override it; the vector is zero-padded or
        truncated only when the requested size differs from the model output.

        Args:
            text: Text to embed.
            output_dimensionality: Target vector length. Padded/truncated as needed.
            task_type: Accepted for API parity; unused (IBM models don't take it).
        """
        del task_type  # signature compatibility only

        _throttle_before_call()
        try:
            embeddings = self._get_embeddings()
            result = embeddings.embed_documents(texts=[text])
        except Exception as e:
            if self._is_auth_error(e):
                self.logger.warning(f"WatsonX embedding auth error — refreshing: {e}")
                self._force_refresh()
                embeddings = self._get_embeddings()
                result = embeddings.embed_documents(texts=[text])
            else:
                self.logger.error(f"Embedding generation failed: {e}")
                raise WatsonXError(f"Embedding generation failed: {e}") from e

        if not result or not result[0]:
            raise WatsonXError("Empty embedding returned from WatsonX API")

        vector: List[float] = list(result[0])

        if output_dimensionality and output_dimensionality != len(vector):
            if len(vector) < output_dimensionality:
                vector = vector + [0.0] * (output_dimensionality - len(vector))
            else:
                self.logger.warning(
                    f"Truncating embedding from {len(vector)} -> {output_dimensionality} dims"
                )
                vector = vector[:output_dimensionality]
        return vector

    def count_tokens(self, text: str) -> int:
        """Return token count via the SDK's tokenize endpoint (falls back to estimate)."""
        try:
            model = self._get_model(self.model_name)
            result = model.tokenize(prompt=text, return_tokens=False)
            if isinstance(result, dict):
                inner = result.get("result", result)
                if isinstance(inner, dict) and "token_count" in inner:
                    return int(inner["token_count"])
        except Exception as e:
            self.logger.debug(f"count_tokens fell back to estimate: {e}")
        return self.estimate_tokens(text)

    def estimate_tokens(self, text: str) -> int:
        """Cheap heuristic: ~4 chars per token."""
        return max(1, len(text) // 4)

    def switch_model(self, model: Literal["flash", "pro"]) -> None:
        """Switch the default model used by `generate()` / `generate_json()`."""
        old_model = self.model_name
        self.default_mode = model
        self.model_name = self._flash_model_id if model == "flash" else self._pro_model_id
        self.logger.info(f"Switched default model: {old_model} -> {self.model_name}")


# Made with Bob
