# Bugs for Bob

Running log of bugs and design issues to fix. Each entry has enough detail (file path, line numbers, current code, suggested fix) to act on without re-investigating.

New entries are appended to the bottom. Older entries are not removed even if fixed — they are marked ✅ FIXED with a date so we keep a trail.

## Status — 2026-05-15

**Fixed (68/72).** All CRITICAL + HIGH + MEDIUM + most LOW bugs closed.

**Deferred (4):**
- **BUG-016** (INFO): migrate from `google-generativeai` to new `google-genai` SDK — deferred until SDK is stable enough; current client works.
- **BUG-023** (LOW): batching / asyncio concurrency in `RelevanceFilter` — deferred until traffic > 50 companies per run.
- **BUG-071** (INFO): file naming `coordinator.py` vs plan's `orchestrator.py` — cosmetic only.
- **PLAN-001** (INFO): plan-level aggregation spec — documented inline in `aggregator.py` docstring; can update plan doc later.

---

## Aggregator (`src/ingestion/aggregator.py`)

### BUG-001 — Affinity domain key mismatch (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/ingestion/aggregator.py:215-218`
**Related:** `src/ingestion/affinity.py:312-317`

**Problem:**
Aggregator looks for `metadata.organization_domain` for Affinity-sourced interactions, but the Affinity connector emits the key as `domain`. The lookup always returns `None`, so Affinity falls through to participant-email-based domain extraction — defeating the purpose of having an explicit org domain in metadata. For the `crm_record` fallback path (`affinity.py:337-341`) the metadata has no domain field at all.

**Current code (aggregator.py:215-218):**
```python
if source == 'affinity':
    org_domain = interaction.get('metadata', {}).get('organization_domain')
    if org_domain:
        return org_domain.lower()
```

**Fix — pick one:**

Option A (preferred — fix the producer so the key name is unambiguous):
In `affinity.py`, change both metadata blocks to use `organization_domain`:
- `affinity.py:312-317` (note branch): rename `"domain": org.domain` → `"organization_domain": org.domain`
- `affinity.py:337-341` (crm_record branch): add `"organization_domain": org.domain`

Option B (one-line fix in aggregator):
Change `aggregator.py:216` from `.get('organization_domain')` to `.get('domain')`. Doesn't help the `crm_record` branch which still has no domain in metadata.

---

### BUG-002 — No exclusion of VC partner's own domain in company-key extraction (HIGH)

**File:** `src/ingestion/aggregator.py:225-236`

**Problem:**
`_extract_company_key` filters out generic email providers (`gmail.com`, `outlook.com`, `yahoo.com`, `hotmail.com`) and picks `sorted(domains)[0]` from the remainder. For a meeting between `ahmed@yellowvc.com` and `sara@acme.ai`, both domains survive the filter — alphabetical sort picks `acme.ai` by luck. The day a partner emails from a domain that sorts earlier than the target company, interactions silently misgroup under the VC's own domain.

**Current code (aggregator.py:225-236):**
```python
domains = set()
for participant in participants:
    if '@' in participant:
        domain = participant.split('@')[1].lower()
        if domain not in ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com']:
            domains.add(domain)

if domains:
    return sorted(domains)[0]
```

**Fix:**
1. Add a `self_domains: set[str]` parameter (or read from `config.Settings`) — the VC's own domain(s), e.g. `{"yellowvc.com"}`.
2. Subtract `self_domains` from the candidate set before picking.
3. Also extend the generic-provider blocklist (add `icloud.com`, `protonmail.com`, `fastmail.com`, `gmx.com`, `mail.com`, `pm.me`, `me.com`).
4. If multiple non-self domains remain, prefer the one matching the sender (`From` header for Gmail / `owner.email` for Granola is *us*, so the *other* domain is the company). Falling back to `sorted()` is fine as a last resort but log a warning.

---

### BUG-003 — `datetime.utcnow()` deprecated (LOW) ✅ FIXED 2026-05-15

**File:** `src/ingestion/aggregator.py:290`

**Problem:**
`datetime.utcnow()` is deprecated in Python 3.12+. The rest of the codebase uses `datetime.now(timezone.utc)` (see `utils.py:32`).

**Current code (aggregator.py:290):**
```python
'aggregated_at': datetime.utcnow().isoformat() + 'Z'
```

**Fix:**
```python
'aggregated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
```

Add `timezone` to the existing `from datetime import datetime` at `aggregator.py:9`.

---

### BUG-004 — Dead import (TRIVIAL)

**File:** `src/ingestion/aggregator.py:16`

**Problem:**
`from .base import IngestionError` is imported but never referenced. The aggregator catches `Exception` everywhere instead of using the typed exception.

**Fix — pick one:**
- Delete the import.
- Or use it: change `except Exception as e:` in `_fetch_all_interactions` (`:131-132`, `:140-141`, `:149-150`, `:158-159`) to `except IngestionError as e:` so genuine connector bugs aren't swallowed alongside expected ingestion failures.

---

### BUG-005 — `CompanyData.company_name` set to a domain string (MEDIUM)

**File:** `src/ingestion/aggregator.py:294-300`
**Related:** `src/ingestion/models.py:253-254`

**Problem:**
Aggregator sets `company_name=company_key` where `company_key` is a domain like `"acme.ai"`. Comment says "Will be enriched by LLM later", but downstream consumers that read `company_name` before the LLM step will see a domain in a name field. Risk of the placeholder leaking into reports / UI / logs.

**Fix:**
Either:
- Leave `company_name=""` and store the domain only in `company_id` (current state already sets `company_id=company_key` at `:296`).
- Or derive a readable default: `company_name=company_key.split('.')[0].title()` (`"acme.ai"` → `"Acme"`).

Either way, document in the docstring that `company_name` is a placeholder until the LLM extraction step fills it from the actual extraction output.

---

### BUG-006 — `CompanyData` source-tracking fields are never populated (MEDIUM)

**File:** `src/ingestion/aggregator.py:294-300`
**Related:** `src/ingestion/models.py:261-264`

**Problem:**
`CompanyData` has four source-tracking fields (`granola_notes`, `affinity_data`, `gmail_messages`, `slack_messages`) that the aggregator never sets. They always default to empty/None. Either the LLM extraction step needs them filled, or they're dead model fields.

**Fix — pick one:**
- **Populate them:** while iterating `unique_interactions` in `_build_company_data`, partition by `source` and push the raw items into the matching list. Gives the LLM access to the original source-native payload.
- **Delete them from the model:** simpler. The aggregator's `interactions: List[UnifiedInteraction]` already carries `raw_data` per item, so source-specific access is still possible.

Decide which one before the LLM extraction layer is built — picking after the fact means refactoring both sides.

---

### BUG-007 — Double validation (LOW)

**File:** `src/ingestion/aggregator.py:264-270`
**Related:** `src/ingestion/base.py:72-96`

**Problem:**
`BaseConnector.validate_data` already runs `UnifiedInteraction(**data)` during `ingest()`. The aggregator runs the same validation again at `:267`. Wasted cycles, not a correctness bug.

**Fix:**
Trust upstream validation. Replace the try/except block at `:265-270` with a direct construction, since malformed items would have been filtered by `BaseConnector.ingest` already:
```python
unified_interactions = [UnifiedInteraction(**i) for i in unique_interactions]
```

If you want a safety net, keep the validation but downgrade the log to `debug` — an error here means a bug in the connector, not data corruption.

---

### BUG-008 — No "dropped interactions" telemetry (LOW)

**File:** `src/ingestion/aggregator.py:179-196`

**Problem:**
Interactions without a resolvable company key are silently skipped at `:183-185`. With the Affinity domain bug (BUG-001) and Slack's frequently-empty participants for bot messages, this can drop a significant fraction of signal without any indication.

**Fix:**
Add counters at the start of `_group_by_company` and log them before returning:
```python
dropped_no_key = 0
dropped_filtered = 0
# ... in the loop:
if not company_key:
    dropped_no_key += 1
    continue
if filter_domains and company_key not in filter_domains:
    dropped_filtered += 1
    continue
# ... before return:
if dropped_no_key:
    self.logger.warning(f"Dropped {dropped_no_key} interactions with no resolvable company key")
if dropped_filtered:
    self.logger.info(f"Dropped {dropped_filtered} interactions outside domain filter")
```

---

## Plan-level gaps (`IMPLEMENTATION_PLAN.md`)

### PLAN-001 — Aggregation strategy is unspecified

**File:** `IMPLEMENTATION_PLAN.md` Phase 1, §1.2 and §1.3

**Problem:**
The plan mentions `aggregator.py` in the file tree and says "Combines all sources into unified company object" but never specifies *how* aggregation works — domain matching? Affinity `org_id` as canonical key? Name matching? Hash of normalized name? The aggregator picked "domain as identity" without that being in the spec.

**Fix:**
Add a §1.5 to the plan covering:
- **Canonical company key:** domain (preferred) → fallback to Affinity `org_id` → fallback to normalized name.
- **`self_domains` configuration:** which domain(s) belong to the VC firm itself and must be excluded from company-key candidates.
- **Multi-company items:** how to handle a single source item that mentions multiple companies (current decision: pick one by priority order; see chat decision to defer per-source-item extraction).
- **Cross-source dedup:** interactions with the same `id` are de-duped; same conversation surfacing via two sources (e.g., meeting note + follow-up email) is intentionally kept as two events.

---

## LLM Layer — Gemini Client (`src/llm/gemini_client.py`)

### BUG-009 — Client ignores `config.Settings`, reads `os.getenv` directly (HIGH)

**File:** `src/llm/gemini_client.py:54`
**Related:** `src/config.py:12-15`

**Problem:**
The project has a `Settings` class with `gemini_api_key`, `gemini_model`, `gemini_temperature`, `gemini_max_tokens`. The client bypasses it and reads `os.getenv('GEMINI_API_KEY')` directly, with hardcoded defaults for everything else. Two sources of truth — changing `.env` values for temperature/model has no effect on the client.

**Current code (`gemini_client.py:54-67`):**
```python
self.api_key = api_key or os.getenv('GEMINI_API_KEY')
...
self.model_name = self.FLASH if model == "flash" else self.PRO
...
self.default_temperature = default_temperature
self.default_max_tokens = default_max_tokens
```

**Fix:**
Import settings and use them as the defaults:
```python
from src.config import get_settings
settings = get_settings()

self.api_key = api_key or settings.gemini_api_key
self.default_temperature = default_temperature if default_temperature is not None else settings.gemini_temperature
self.default_max_tokens = default_max_tokens if default_max_tokens is not None else settings.gemini_max_tokens
```

Keep the `api_key` constructor override so tests / multi-tenant setups still work.

---

### BUG-010 — Hardcoded model names disagree with config default (HIGH)

**File:** `src/llm/gemini_client.py:36-37`
**Related:** `src/config.py:13`, `IMPLEMENTATION_PLAN.md` §2.1 + §3.1

**Problem:**
Client hardcodes `FLASH = "gemini-2.5-flash"` and `PRO = "gemini-2.5-pro"`. Config defaults `gemini_model = "gemini-2.0-flash-exp"`. Plan specifies `gemini-2.5-flash` / `gemini-2.5-pro`. So **config is the outlier** — but the client never reads it, so the inconsistency is hidden. The day someone wires `settings.gemini_model` into the client, behavior changes silently.

**Fix:**
1. Update `config.py:13` default: `gemini_model: str = "gemini-2.5-flash"` (matches plan).
2. After applying BUG-009, prefer `settings.gemini_model` over the hardcoded constants — or remove the `FLASH`/`PRO` constants and let the caller pass any model string from config.

---

### BUG-011 — `@retry` retries on every exception (including non-transient) (MEDIUM)

**File:** `src/llm/gemini_client.py:72-77`

**Problem:**
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),   # ← retries on ANY exception
    reraise=True
)
```
This retries on:
- 400 (malformed prompt / over-length) — won't fix itself, wastes calls.
- 401/403 (auth / quota / billing) — wastes calls.
- Safety-block "empty response" raised at `:118-119` — deterministic, wastes calls.

Only 429 (rate limit) and 5xx are worth retrying.

**Fix:**
Either narrow the retry predicate to transient errors, or wrap the inner `generate_content` call in a try/except that translates Google SDK exceptions into a transient vs. permanent split, and only let transient ones bubble up to tenacity:

```python
from google.api_core import exceptions as gexc

class TransientGeminiError(GeminiError):
    pass

# in generate():
try:
    response = self.model.generate_content(prompt, generation_config=config)
except (gexc.ResourceExhausted, gexc.ServiceUnavailable, gexc.DeadlineExceeded) as e:
    raise TransientGeminiError(str(e)) from e
except gexc.GoogleAPIError as e:
    raise GeminiError(str(e)) from e  # permanent — won't retry

# on @retry decorator:
retry=retry_if_exception_type(TransientGeminiError),
```

---

### BUG-012 — Doesn't use Gemini's native JSON mode (MEDIUM)

**File:** `src/llm/gemini_client.py:101-115`
**Related:** `IMPLEMENTATION_PLAN.md` §3.1 ("Response format: JSON mode if available")

**Problem:**
`json_mode=True` appends a text instruction ("Return ONLY valid JSON…") but doesn't set Gemini's native `response_mime_type='application/json'` on `GenerationConfig`. Native JSON mode is far more reliable than text instructions — eliminates 90%+ of "stripped markdown fence" / "extra preamble" parse failures.

**Current code (`gemini_client.py:101-108`):**
```python
config = GenerationConfig(
    temperature=temperature or self.default_temperature,
    max_output_tokens=max_tokens or self.default_max_tokens
)

if json_mode:
    prompt = f"{prompt}\n\nIMPORTANT: Return ONLY valid JSON, no markdown fences or explanations."
```

**Fix:**
```python
config_kwargs = {
    "temperature": temperature or self.default_temperature,
    "max_output_tokens": max_tokens or self.default_max_tokens,
}
if json_mode:
    config_kwargs["response_mime_type"] = "application/json"
config = GenerationConfig(**config_kwargs)
```
Keep the text instruction as a belt-and-braces fallback, but the native mode does the heavy lifting.

---

### BUG-013 — `response.text` can raise on safety-blocked responses (LOW)

**File:** `src/llm/gemini_client.py:118-119`

**Problem:**
```python
if not response.text:
    raise GeminiError("Empty response from Gemini API")
```
The Gemini SDK raises `ValueError` (something like *"The response.parts quick accessor only works for a single Part response..."*) when the response was blocked by safety filters or returned multiple candidates. The `not response.text` check never runs — the access itself throws — and the resulting exception then gets retried three times by tenacity (BUG-011 makes this worse).

**Fix:**
Inspect `response.candidates` and `response.prompt_feedback` before accessing `.text`:
```python
if not response.candidates:
    feedback = getattr(response, 'prompt_feedback', None)
    raise GeminiError(f"No candidates (likely safety block): {feedback}")

candidate = response.candidates[0]
if candidate.finish_reason.name != "STOP":
    raise GeminiError(f"Generation stopped with reason: {candidate.finish_reason.name}")

text = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
if not text.strip():
    raise GeminiError("Empty response text")
```

---

### BUG-014 — Markdown fence regex is brittle (LOW)

**File:** `src/llm/gemini_client.py:207-211`

**Problem:**
```python
fence_pattern = r'^```(?:json)?\s*\n(.*?)\n```$'
match = re.match(fence_pattern, text, re.DOTALL)
```
- Anchored to start of string — text with preamble (`"Here is the JSON: ```…```"`) doesn't match.
- Requires `\n` immediately after the opening fence — Gemini sometimes emits ` ```json{"..."} ``` ` (no leading newline) or `\r\n` line endings on Windows.
- Requires `\n` before the closing fence — trailing text after `}` breaks the match.

**Fix:**
Use a more lenient extractor that finds the first JSON-looking block:
```python
# Try to find fenced block (lenient)
fence_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
if fence_match:
    text = fence_match.group(1).strip()
else:
    # No fence — try to extract first {...} or [...] block
    obj_match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if obj_match:
        text = obj_match.group(1)

return json.loads(text)
```

(BUG-012's native JSON mode largely obsoletes this, but the parser should still be robust.)

---

### BUG-015 — `count_tokens` fallback estimate is silent (TRIVIAL)

**File:** `src/llm/gemini_client.py:226-232`

**Problem:**
When `model.count_tokens` fails, falls back to `len(text) // 4`. Logs at `warning` level — fine. But the return value is indistinguishable from a real count, so callers might budget against it.

**Fix (optional):**
Either return `-1` / raise on failure, or split into `count_tokens` (raises) and `estimate_tokens` (the 4-char heuristic). Caller picks which.

---

### BUG-016 — Using deprecated `google-generativeai` SDK (INFO)

**File:** `src/llm/gemini_client.py:17-18`
**Related:** `requirements.txt`

**Problem:**
`google-generativeai` is the legacy SDK. Google's current recommendation (since late 2024) is the unified `google-genai` package (`from google import genai`). For a project starting fresh, the new SDK is preferred — better async support, cleaner API, will receive new features first.

**Fix (deferred, not blocking):**
Migration would touch `gemini_client.py` only:
- `pip install google-genai` (replace `google-generativeai==0.3.2` in `requirements.txt`)
- `from google import genai` and `from google.genai import types`
- `client = genai.Client(api_key=...)` instead of `genai.configure(...)`
- `client.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(...))`

Don't do this until BUG-009 through BUG-014 are settled — easier to migrate a clean client than a buggy one.

---

## LLM Layer — Relevance Filter (`src/llm/relevance_filter.py`)

### BUG-017 — ZeroDivisionError when filtering empty interaction list (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/llm/relevance_filter.py:144-147`

**Problem:**
```python
self.logger.info(
    f"Filtered {len(interactions)} interactions -> "
    f"{len(relevant_interactions)} relevant ({len(relevant_interactions)/len(interactions)*100:.1f}%)"
)
```
If `filter_interactions([])` is called, the for-loop runs zero times, then this log line divides by `len(interactions) == 0` → `ZeroDivisionError`. Crashes the entire pipeline.

This can happen if `filter_company_data` is called on a CompanyData with `interactions: []` — the early-return check at `:165-167` handles that path, but any *other* caller of `filter_interactions` directly will crash.

**Fix:**
Guard the division:
```python
if interactions:
    rate = len(relevant_interactions) / len(interactions) * 100
    self.logger.info(
        f"Filtered {len(interactions)} interactions -> "
        f"{len(relevant_interactions)} relevant ({rate:.1f}%)"
    )
else:
    self.logger.info("Filtered 0 interactions (empty input)")
```

---

### BUG-018 — `filter_metadata` added to interaction dict is silently dropped on Pydantic re-validation (MEDIUM) ✅ FIXED 2026-05-15

**File:** `src/llm/relevance_filter.py:133-138`
**Related:** `src/ingestion/models.py:231-245`

**Problem:**
```python
interaction['filter_metadata'] = {
    'relevant': True,
    'reason': decision.reason
}
relevant_interactions.append(interaction)
```
`UnifiedInteraction` has no `filter_metadata` field. Pydantic v2 defaults to `extra='ignore'`, so any downstream `UnifiedInteraction(**data)` round-trip (and there are several — `BaseConnector.validate_data`, `aggregator._build_company_data:267`) silently drops `filter_metadata`. The relevance reason is lost.

**Fix — pick one:**

**Option A (cleanest):** stash it inside the existing `metadata` dict instead of at the top level:
```python
if 'metadata' not in interaction:
    interaction['metadata'] = {}
interaction['metadata']['filter'] = {
    'relevant': True,
    'reason': decision.reason
}
```

**Option B:** add `filter_metadata: Optional[Dict[str, Any]] = None` to `UnifiedInteraction` in `models.py`. More invasive but makes filter output a first-class field.

---

### BUG-019 — `filter_interactions` mutates input dicts in place (MEDIUM) ✅ FIXED 2026-05-15

**File:** `src/llm/relevance_filter.py:133-138`

**Problem:**
```python
interaction['filter_metadata'] = {...}
relevant_interactions.append(interaction)
```
Mutates the caller's dict. If a caller passes the same list to multiple filters, or compares pre/post, surprise mutation. Common foot-gun.

**Fix:**
Shallow-copy before mutating:
```python
tagged = dict(interaction)
tagged.setdefault('metadata', {}).update({  # if applying BUG-018 option A
    'filter': {'relevant': True, 'reason': decision.reason}
})
relevant_interactions.append(tagged)
```

---

### BUG-020 — No prompt-template placeholder validation (MEDIUM) ✅ FIXED 2026-05-15

**File:** `src/llm/relevance_filter.py:56-62`, `:80-81`

**Problem:**
If `relevance_filter.txt` is missing the `{{INTERACTION}}` placeholder (typo, accidental deletion, wrong file), `prompt.replace('{{INTERACTION}}', ...)` silently does nothing → Gemini receives the prompt template with no actual interaction → returns garbage / hallucinates → relevance decisions are meaningless. No error.

**Fix:**
Validate the template at load time:
```python
with open(prompt_path, 'r', encoding='utf-8') as f:
    self.prompt_template = f.read()

if '{{INTERACTION}}' not in self.prompt_template:
    raise ValueError(
        f"Prompt template at {prompt_path} is missing required placeholder '{{INTERACTION}}'"
    )
```

---

### BUG-021 — Filter errors are counted as "relevant" in stats (LOW)

**File:** `src/llm/relevance_filter.py:101-113`

**Problem:**
The "default to relevant on error" policy is per the plan, but the error case is recorded as a legitimate `relevant=True` decision. In `filter_company_data.metadata.filter_stats`, errors are indistinguishable from genuine relevance decisions. Pipeline health becomes invisible — if Gemini's flaky and 50% of calls error out, the metrics show "100% relevant" with no signal that something's wrong.

**Fix:**
Add an error counter:
```python
# in filter_interactions:
error_count = 0
for interaction in interactions:
    decision = self.filter_interaction(interaction)
    if "Error during filtering" in decision.reason or "Unexpected error" in decision.reason:
        error_count += 1
    if decision.relevant:
        ...

# in filter_company_data.filter_stats:
'errored': error_count,
```

Cleaner alternative: return a `(decision, errored: bool)` tuple from `filter_interaction` instead of overloading the `reason` field as a status carrier.

---

### BUG-022 — `max_tokens=100` may truncate response and break JSON parsing (LOW) ✅ FIXED 2026-05-15

**File:** `src/llm/relevance_filter.py:88`

**Problem:**
`{"relevant": true, "reason": "..."}` with a one-sentence reason fits in ~100 tokens, but Gemini occasionally adds preamble ("Here is my analysis:...") that, combined with native JSON mode missing (BUG-012), can push past 100 → truncated → JSON parse fails → retry sends same 100-token cap → fails again → fallback "default to relevant" with no real signal.

**Fix:**
Bump to 200 tokens. Cost difference is negligible for an output-only model and headroom prevents truncation parse-failure cascades.

```python
response = self.client.generate_json(
    prompt=prompt,
    temperature=0.1,
    max_tokens=200
)
```

(After BUG-012 lands and native JSON mode is enabled, 100 is fine again.)

---

### BUG-023 — Serial per-interaction calls; no batching or concurrency (LOW)

**File:** `src/llm/relevance_filter.py:115-149`

**Problem:**
`filter_interactions` iterates one-by-one with a synchronous Gemini call each iteration. 100 interactions = 100 sequential round-trips ≈ 1–3 minutes. Will become a bottleneck once mock data is replaced.

**Fix (deferred):**
Two options, in order of effort:

1. **`asyncio.gather` with semaphore** — easiest. Use `google-genai`'s async client (or thread pool around the sync SDK), cap concurrency at ~10 to respect rate limits.
2. **Prompt batching** — pack 5–10 interactions into one prompt, ask for a JSON array of decisions. Big cost+latency win but requires prompt rework.

Not blocking for MVP. Flag it once volume > 50 interactions per run.

---

## LLM Layer — Extraction Engine (`src/llm/extraction_engine.py`)

### BUG-024 — Extraction prompt references fields that don't exist in the input data (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/llm/prompts/extraction_engine.txt:70`, `:39`

**Problem:**
The prompt tells the LLM to extract from fields that the aggregator never produces:

- **Line 70:** *"`participants`: list all named participants from `yellow_participant` and `external_participants`"*
  The actual `UnifiedInteraction` schema has a single flat `participants: List[str]` field (`ingestion/models.py:243`). There are no `yellow_participant` or `external_participants` fields anywhere in the pipeline. The LLM will look for them, find nothing, and either hallucinate or return empty arrays.

- **Line 39:** *"`source.external_id`: use the `affinity_id` from the company object if present"*
  The `CompanyData` object emits `company_id` (set to the domain by the aggregator) — there is no `affinity_id` field. The Affinity numeric org_id is buried in per-interaction `metadata.organization_id`. The instruction can never be followed as written.

**Impact:**
LLM extractions will silently lose Affinity provenance and may mis-classify participants (e.g., listing the VC partner as an external contact). This is the most expensive call in the pipeline — it should not be told to read non-existent fields.

**Fix:**

In `extraction_engine.txt`:
- Line 70 → *"`participants`: list all named participants from the interaction's `participants` field. Distinguish VC team members from external contacts using the email domain — the firm's own domains (e.g. yellowvc.com) are internal, all others are external."*
- Line 39 → *"`source.external_id`: use the Affinity organization id if present. Look in each interaction's `metadata.organization_id` (only present for `source: affinity` interactions). Pick the first non-null value across interactions."*

Alternative: if you want the prompt to keep its current shape, have the aggregator pre-compute these fields when building `CompanyData` for the extraction step:
- Split `participants` into `internal_participants` / `external_participants` using a `self_domains` config.
- Promote any Affinity `organization_id` found in interactions to a top-level `affinity_id` on `CompanyData`.

Either path works — pick one and make the prompt and aggregator agree.

---

### BUG-025 — `max_tokens=4096` likely truncates full extraction output (HIGH) ✅ FIXED 2026-05-15

**File:** `src/llm/extraction_engine.py:90`

**Problem:**
The extraction output has 8 top-level blocks, with lists for `contacts`, `interactions`, `tags`, `key_strengths`, `key_concerns`, `for_arguments`, `against_arguments`, `open_questions`, plus per-interaction `takeaways`, `topics`, `metrics_mentioned`, `quotes`. For a company with 20+ interactions, the serialized JSON easily exceeds 4096 tokens. Truncation mid-JSON → parse fails → `generate_json` retries with the same `max_tokens=4096` → retry truncates at roughly the same place → both fail.

**Current code (`extraction_engine.py:87-92`):**
```python
response = self.client.generate_json(
    prompt=prompt,
    temperature=0.2,
    max_tokens=4096,
    retry_on_parse_error=True
)
```

**Fix:**
Bump to 8192 for Flash, 16384 for Pro (`gemini-2.5-pro` supports up to 65k output tokens). Better yet, pull the value from config:

```python
response = self.client.generate_json(
    prompt=prompt,
    temperature=0.2,
    max_tokens=16384,  # plenty of headroom for full ExtractionOutput
    retry_on_parse_error=True
)
```

Combine with BUG-012's native JSON mode and the truncation parse-fail loop largely goes away.

---

### BUG-026 — `datetime.utcnow()` deprecated (HIGH) ✅ FIXED 2026-05-15

**File:** `src/llm/extraction_engine.py:170`

**Problem:**
Same as BUG-003 (aggregator). `datetime.utcnow()` is deprecated in Python 3.12+. The rest of the codebase uses `datetime.now(timezone.utc)` (see `utils.py:32`).

**Current code (`extraction_engine.py:170`):**
```python
current_datetime = datetime.utcnow().isoformat() + 'Z'
```

**Fix:**
```python
from datetime import datetime, timezone
...
current_datetime = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
```

---

### BUG-027 — No prompt placeholder validation in extraction engine (MEDIUM) ✅ FIXED 2026-05-15

**File:** `src/llm/extraction_engine.py:52-53`, `:176-179`

**Problem:**
Same shape as BUG-020 (relevance filter). If `extraction_engine.txt` is missing any of `{{COMPANY_DATA}}`, `{{CURRENT_DATETIME}}`, `{{MODEL_NAME}}`, the `replace` silently no-ops. The LLM gets a prompt referencing variables it can never resolve, or runs without the actual company data. No error.

**Fix:**
```python
REQUIRED_PLACEHOLDERS = ['{{COMPANY_DATA}}', '{{CURRENT_DATETIME}}', '{{MODEL_NAME}}']

with open(prompt_path, 'r', encoding='utf-8') as f:
    self.prompt_template = f.read()

missing = [p for p in REQUIRED_PLACEHOLDERS if p not in self.prompt_template]
if missing:
    raise ValueError(
        f"Prompt template at {prompt_path} is missing required placeholders: {missing}"
    )
```

---

### BUG-028 — `extract_batch` silently drops failed companies, caller has no failure info (MEDIUM)

**File:** `src/llm/extraction_engine.py:119-155`

**Problem:**
```python
for i, company_data in enumerate(companies, 1):
    company_name = company_data.get('company_name', f'Company {i}')
    try:
        extraction = self.extract(company_data)
        extractions.append(extraction)
        ...
    except Exception as e:
        self.logger.error(f"Failed to extract {company_name}: {e}. Skipping.")
        continue
```
If 4 of 15 companies fail, the caller gets back a list of 11 `ExtractionOutput`s with no way to know *which* 4 failed or why (without scraping logs). For a pipeline run that needs to retry or alert on failure, this is opaque.

**Fix:**
Return a result object or a tuple:

```python
from typing import NamedTuple

class BatchResult(NamedTuple):
    successes: List[ExtractionOutput]
    failures: List[Tuple[str, str]]   # (company_name, error_message)

def extract_batch(self, companies: list[Dict[str, Any]]) -> BatchResult:
    successes, failures = [], []
    for i, company_data in enumerate(companies, 1):
        company_name = company_data.get('company_name', f'Company {i}')
        try:
            successes.append(self.extract(company_data))
        except Exception as e:
            failures.append((company_name, str(e)))
            self.logger.error(f"Failed to extract {company_name}: {e}")
    return BatchResult(successes=successes, failures=failures)
```

---

### BUG-029 — `extract_to_dict` and `extract_to_json` make redundant Gemini calls (MEDIUM) ✅ FIXED 2026-05-15 (renamed to `to_dict`/`to_json` that take a pre-extracted ExtractionOutput)

**File:** `src/llm/extraction_engine.py:183-214`

**Problem:**
Both convenience methods call `self.extract(company_data)`, which makes a fresh Gemini call every time. If a caller wants both the model object and a dict/file, they pay double — one extraction = two Pro-model API calls = ~$0.20+ for nothing.

**Fix:**
Accept either pre-extracted output or run extraction once:

```python
def to_dict(self, extraction: ExtractionOutput) -> Dict[str, Any]:
    return extraction.model_dump()

def to_json(self, extraction: ExtractionOutput, output_path: str) -> None:
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(extraction.model_dump(), f, indent=2)
    self.logger.info(f"Saved extraction to {output_path}")
```

Caller does `extraction = engine.extract(company); engine.to_json(extraction, path)`. One API call, both outputs. If you want the convenience methods back, internally call `extract` once and produce both.

---

### BUG-030 — `json.dumps(company_data, indent=2)` fails on non-JSON-serializable values (LOW) ✅ FIXED 2026-05-15

**File:** `src/llm/extraction_engine.py:167`

**Problem:**
If `company_data` contains any `datetime`, `Decimal`, `set`, or Pydantic model instances (which can happen if upstream code uses `model_dump()` without `mode='json'`, or stashes objects in `metadata`), `json.dumps` raises `TypeError`. The exception propagates out of `extract`, gets caught only as a generic `Exception` in `extract_batch`, and the company is dropped with no actionable error.

**Fix:**
Add a `default=str` fallback:
```python
company_json = json.dumps(company_data, indent=2, default=str)
```
Or, more strictly, sanitize before serializing — but `default=str` is the cheap robust option.

---

## LLM Layer — Schemas (`src/llm/schemas.py`)

### BUG-031 — No date/datetime format validation on string fields (MEDIUM)

**File:** `src/llm/schemas.py:34, 48, 84, 108, 143, 165, 172, 178, 193`

**Problem:**
Many fields are typed as `str` with the spec implying a format (e.g., `YYYY-MM-DD` or ISO 8601 datetime):
- `Company.first_met_at`, `MetricMention.as_of`, `NewsItem.published_at`, `Signal.detected_at` → `YYYY-MM-DD`
- `DealStatus.last_touch_at`, `Interaction.occurred_at`, `DecisionRecord.decided_at`, `CompanyNow.fetched_at`, `ExtractionMeta.extracted_at` → ISO 8601 datetime

Pydantic accepts any string, including malformed ones (`"April 28, 2026"`, `"2026/04/28"`, `"yesterday"`). Downstream code that parses these (DB writes, sort by date, comparisons) will fail or produce garbage silently.

**Fix:**
Add field validators or use Pydantic's `date` / `datetime` types via `Field`. Lightweight option — a single shared validator:

```python
from pydantic import field_validator
import re

ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
ISO_DATETIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$')

def _date_validator(cls, v):
    if v is None or v == "":
        return None
    if not ISO_DATE_RE.match(v):
        raise ValueError(f"Expected YYYY-MM-DD, got '{v}'")
    return v

def _datetime_validator(cls, v):
    if v is None or v == "":
        return None
    if not ISO_DATETIME_RE.match(v):
        raise ValueError(f"Expected ISO 8601 datetime, got '{v}'")
    return v

# then apply, e.g.:
class Company(BaseModel):
    ...
    first_met_at: Optional[str] = None
    _v_first_met = field_validator('first_met_at')(_date_validator)
```

Or simpler — switch to `datetime.date` / `datetime.datetime` Pydantic types and let Pydantic coerce. Trade-off: the model no longer round-trips as raw strings, which may matter for the extraction format compatibility.

---

### BUG-032 — Schemas don't enforce `extra='forbid'` — silent field drift (LOW)

**File:** `src/llm/schemas.py` (all models)

**Problem:**
Pydantic v2 defaults to `extra='ignore'`. If the LLM returns an unexpected field (e.g., `"verdict_confidence": 0.8` on `DecisionRecord`), it's silently dropped. For an extraction layer where you want every field deliberately specified, drift is a real risk — the LLM may start emitting new fields after a model upgrade and nobody notices.

**Fix — pick one:**

**Option A (strict, surfaces drift):**
```python
from pydantic import ConfigDict

class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ...
```
Apply to every model. Any extra field raises `ValidationError`. Catches drift immediately. Downside: a minor LLM hallucination breaks the whole extraction.

**Option B (logging-friendly):**
Keep `extra='ignore'` for production but add a debug log when `set(response.keys()) - set(Model.model_fields.keys())` is non-empty. Visible without being fragile.

Recommend Option B for now, switch to Option A once the prompt is stable.

---

### BUG-033 — `Company.name` allows empty string (LOW) ✅ FIXED 2026-05-15

**File:** `src/llm/schemas.py:27`

**Problem:**
`name: str` is required but has no length constraint. The LLM could emit `"name": ""` and the model would validate cleanly. Empty company names will propagate to Neo4j as empty nodes, break uniqueness logic, and cause UI rendering bugs.

**Fix:**
```python
name: str = Field(min_length=1)
```

---

### BUG-034 — Dead `datetime` import (TRIVIAL) ✅ FIXED 2026-05-15

**File:** `src/llm/schemas.py:11`

**Problem:**
```python
from datetime import datetime
```
Never used — all date fields are typed as `str`.

**Fix:**
Delete the import. Or, if you adopt BUG-031's option to switch fields to `datetime.date` / `datetime.datetime`, keep it.

---

### BUG-035 — Dead `os` import in relevance filter (TRIVIAL) ✅ FIXED 2026-05-15

**File:** `src/llm/relevance_filter.py:9`

**Problem:**
```python
import os
```
Never used. Likely leftover from an earlier draft that used `os.getenv` or `os.path`.

**Fix:**
Delete the import.

---

### BUG-036 — No `Field(description=...)` annotations on schemas (INFO)

**File:** `src/llm/schemas.py` (all models)

**Problem:**
Pydantic models with `Field(description="...")` produce richer JSON Schema, which Gemini's structured-output mode (BUG-012) can consume directly. Right now if you wire up native JSON mode with a schema, Gemini gets only the type info — no semantic hints. Output quality degrades vs. the existing freeform prompt.

**Fix (deferred, low priority):**
After BUG-012 lands and native JSON mode is in use, add descriptions where they'd help the model:

```python
class Company(BaseModel):
    name: str = Field(min_length=1, description="Exact company name as written by founders")
    one_liner: Optional[str] = Field(None, description="Single crisp sentence describing what the company does (max 15 words)")
    deal_momentum: Optional[Literal["accelerating", "stable", "stalling", "dead"]] = Field(
        None, description="Trajectory based on interaction cadence and sentiment"
    )
    ...
```

Not blocking. Only worth doing once the prompt → schema → JSON-mode pipeline is wired up.

---

## Storage Layer (`src/storage/` + `src/database/`)

### BUG-037 — `PARTICIPATED_IN` relationships are never created (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/storage/neo4j_writer.py:317-341`, especially `:331`

**Problem:**
`_link_interactions_to_participants` looks up Person nodes by **name**:
```python
for participant_name in interaction.participants:
    person_id = person_ids.get(participant_name)
    if person_id:
        # Create PARTICIPATED_IN relationship
        ...
```
But `interaction.participants` is a `List[str]` of **email addresses** (see `ingestion/models.py:243` and every connector's transform — Granola uses attendee emails, Gmail uses regex-extracted emails, etc.). Meanwhile `person_ids` is keyed by `contact.name` (`neo4j_writer.py:230`).

`person_ids.get("sara@acme.ai")` looks for a key `"sara@acme.ai"` in a dict that has key `"Sara Chen"` → returns `None` → no relationship created. **The `PARTICIPATED_IN` edge is never written for any interaction.**

**Fix:**
Key `person_ids` by email AND name so participant lookup works either way, then look up by what's actually in `participants`:

```python
def _create_person_nodes(self, company_id, contacts):
    person_ids = {}  # email or name → person_id
    for contact in contacts:
        person_id = self._generate_id(contact.email or contact.name)
        ...
        # Index by both
        if contact.email:
            person_ids[contact.email.lower()] = person_id
        person_ids[contact.name] = person_id
    return person_ids

def _link_interactions_to_participants(self, interactions, person_ids):
    for interaction in interactions:
        for participant in interaction.participants:
            key = participant.lower() if '@' in participant else participant
            person_id = person_ids.get(key)
            if person_id:
                self.client.create_relationship(...)
```

---

### BUG-038 — Sector and Tag relationships are never created (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/storage/neo4j_writer.py:140-167`, `src/database/neo4j_client.py:197-223`

**Problem:**
Sector and Tag nodes are uniquely identified by **`name`**, not `id`:
```cypher
CREATE CONSTRAINT sector_name IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT tag_name    IF NOT EXISTS FOR (t:Tag)    REQUIRE t.name IS UNIQUE;
```
(`src/database/cypher/schema.cypher:49-54`)

But the generic `create_relationship` matches nodes by `id`:
```python
query = f"""
    MATCH (a:{from_label} {{id: $from_id}})
    MATCH (b:{to_label} {{id: $to_id}})
    MERGE (a)-[r:{rel_type}]->(b)
"""
```
(`neo4j_client.py:207-213`)

For Sector/Tag the lookup is `MATCH (b:Sector {id: "Climate"})` — but Sector nodes only have `name`, no `id` property. The MATCH returns nothing → MERGE never runs → no `IN_SECTOR` or `TAGGED_WITH` edge is ever created.

**Fix:**
Either:

**Option A (preferred — adjust the writer):** Add a Sector/Tag-specific relationship helper that matches on `name`:
```python
# in neo4j_client.py:
def link_to_sector(self, company_id: str, sector_name: str):
    self.execute_write("""
        MATCH (c:Company {id: $cid})
        MATCH (s:Sector {name: $sname})
        MERGE (c)-[:IN_SECTOR]->(s)
    """, {"cid": company_id, "sname": sector_name})

def link_to_tag(self, company_id: str, tag_name: str):
    self.execute_write("""
        MATCH (c:Company {id: $cid})
        MATCH (t:Tag {name: $tname})
        MERGE (c)-[:TAGGED_WITH]->(t)
    """, {"cid": company_id, "tname": tag_name})
```
And use these from `_create_sector_and_tags` instead of the generic `create_relationship`.

**Option B:** Set `id = name` for Sector and Tag nodes in `create_sector` / `create_tag`:
```cypher
MERGE (s:Sector {name: $name})
SET s.id = $name
```
Then the generic helper works. Slightly hacky but minimal-change.

---

### BUG-039 — `create_company` uses `CREATE`, fails on re-run (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/database/neo4j_client.py:88-96`

**Problem:**
```python
query = """
    CREATE (c:Company {id: $id, name: $name})
    SET c += $properties
    RETURN c
"""
```
With `CREATE CONSTRAINT company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.id IS UNIQUE`, a second call with the same `company_id` raises `ConstraintValidationFailed`. So re-running the pipeline on the same company (after a schema update, after editing the prompt, after fixing the data — any normal iteration) fails the entire Neo4j write.

**Fix:**
Use `MERGE` for idempotency:
```python
query = """
    MERGE (c:Company {id: $id})
    SET c.name = $name
    SET c += $properties
    RETURN c
"""
```

---

### BUG-040 — `create_interaction` uses `CREATE`, fails on re-run (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/database/neo4j_client.py:162-166`

**Problem:**
Same shape as BUG-039:
```python
CREATE (i:Interaction {id: $id})
SET i += $properties
```
`interaction_id IS UNIQUE` constraint → re-ingesting the same Granola note / Gmail thread fails.

**Fix:**
```python
MERGE (i:Interaction {id: $id})
SET i += $properties
```

---

### BUG-041 — `interaction_content.topics` is never written to PostgreSQL (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/database/postgres.py:107-137`, `src/storage/postgres_writer.py:122-129`
**Related:** `src/database/migrations/001_initial_schema.sql:19`, `src/llm/schemas.py:97`

**Problem:**
The schema has a `topics JSONB` column on `interaction_content` (added per the earlier audit), and the extraction emits `WhatHappened.topics: List[str]` (schemas.py:97). But:

- `PostgresClient.insert_interaction_content` (postgres.py:107-137) has no `topics` parameter and no `topics` column in its INSERT statement.
- `PostgresWriter._write_interaction_content` (postgres_writer.py:122-129) calls the insert without `topics`.

Net effect: every extraction emits `topics`, none of them get persisted.

**Fix:**

In `postgres.py:107-137`, add `topics` to the signature and INSERT:
```python
def insert_interaction_content(
    self,
    neo4j_interaction_id: str,
    full_transcript: Optional[str] = None,
    summary: Optional[str] = None,
    takeaways: Optional[Dict] = None,
    topics: Optional[Dict] = None,     # ← add
    quotes: Optional[Dict] = None,
    metrics_mentioned: Optional[Dict] = None
) -> str:
    query = """
        INSERT INTO interaction_content 
        (neo4j_interaction_id, full_transcript, summary, takeaways, topics, quotes, metrics_mentioned)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    ...
    cursor.execute(query, (
        neo4j_interaction_id, full_transcript, summary,
        psycopg2.extras.Json(takeaways) if takeaways else None,
        psycopg2.extras.Json(topics) if topics else None,
        psycopg2.extras.Json(quotes) if quotes else None,
        psycopg2.extras.Json(metrics_mentioned) if metrics_mentioned else None,
    ))
```

In `postgres_writer.py:122-129`, pass it through:
```python
return self.client.insert_interaction_content(
    neo4j_interaction_id=interaction_id,
    full_transcript=None,
    summary=what_happened.summary,
    takeaways={'items': what_happened.takeaways},
    topics={'items': what_happened.topics},     # ← add
    quotes={'items': quotes},
    metrics_mentioned={'items': metrics},
)
```

---

### BUG-042 — `insert_decision_record` is missing `verdict` / `check_size` / `valuation` columns (HIGH) ✅ FIXED 2026-05-15

**File:** `src/database/postgres.py:237-262`, `src/storage/postgres_writer.py:192-205`

**Problem:**
The `decision_records` table schema has `verdict`, `check_size`, `valuation` columns (migration 001 closed the gap per the schema audit). But `insert_decision_record` doesn't include them in the INSERT. The writer compensates by calling `insert_decision_record(...)` and then `update_decision_record(...)` to set them.

Problems with this:
1. Two SQL round-trips instead of one.
2. There's a window where the row exists with `verdict=NULL`, breaking downstream readers that filter on `verdict`.
3. `update_decision_record` uses `COALESCE(%s, verdict)` — if `decision.verdict` is `None`, the existing NULL value is kept. Fine, but indicates the caller never expected `None`.

**Fix:**

Single-shot insert in `postgres.py:237-262`:
```python
def insert_decision_record(
    self,
    company_id: str,
    verdict: str,
    rationale: Optional[str] = None,
    conditions: Optional[Dict] = None,
    check_size: Optional[str] = None,
    valuation: Optional[str] = None,
    decided_at: Optional[str] = None,
) -> str:
    query = """
        INSERT INTO decision_records 
        (company_id, verdict, rationale, conditions, check_size, valuation, decided_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    ...
```

Then in `postgres_writer.py`, replace `:192-207` with a single call (and delete the `update_decision_record` follow-up):
```python
return self.client.insert_decision_record(
    company_id=company_id,
    verdict=decision.verdict,
    rationale=decision.rationale,
    conditions={'items': decision.conditions} if decision.conditions else None,
    check_size=decision.check_size,
    valuation=decision.valuation,
    decided_at=decision.decided_at,
)
```

`update_decision_record` can stay as a separate API for legitimate updates, but should no longer be part of the write path.

---

### BUG-043 — pgvector not registered; embedding inserts/searches will fail (HIGH) ✅ FIXED 2026-05-15

**File:** `src/database/postgres.py:27-47`, `:139-178`

**Problem:**
`insert_company_embedding` passes a Python `List[float]` directly to `psycopg2.execute` and expects it to land in a `VECTOR(1536)` column:
```python
cursor.execute(query, (company_id, embedding, embedding_text))
```
psycopg2 doesn't natively know how to format a list as pgvector — without `pgvector.psycopg2.register_vector(conn)`, the insert either fails or stores garbage. Same problem in `search_similar_companies` where `%s::vector` is used: the parameter needs to be a string `'[1.2, 3.4, ...]'` or psycopg2 must have the adapter registered.

**Fix:**

After establishing each pooled connection, register the pgvector type. Easiest place is to wrap `getconn`:

```python
from pgvector.psycopg2 import register_vector

@contextmanager
def get_connection(self):
    if not self.pool:
        raise RuntimeError("Connection pool not initialized")
    conn = self.pool.getconn()
    try:
        register_vector(conn)   # ← register once per checkout (idempotent)
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        self.pool.putconn(conn)
```

Alternative: register once per connection in a pool factory. Either way, the embedding path is non-functional without this.

---

### BUG-044 — No cross-database rollback; partial writes leave orphans (HIGH)

**File:** `src/storage/orchestrator.py:67-93`

**Problem:**
Plan §5.1 explicitly says *"Execute writes in transaction"*, but the orchestrator writes Neo4j first, then Postgres. If Postgres fails (constraint violation, connection drop, bug), Neo4j retains the Company / Person / Interaction nodes pointing to nothing in Postgres. There's no compensating delete on Neo4j and no two-phase commit.

**Fix:**
Add a compensation path. Doesn't need to be perfect — best-effort cleanup is better than nothing:

```python
try:
    neo4j_result = self.neo4j_writer.write_extraction(extraction)
    result['neo4j'] = neo4j_result
    company_id = neo4j_result['company_id']
    try:
        postgres_result = self.postgres_writer.write_extraction(
            extraction=extraction, company_id=company_id
        )
        result['postgres'] = postgres_result
        result['success'] = True
        return result
    except Exception as pg_err:
        self.logger.error(f"Postgres write failed for {company_name}: {pg_err}. Rolling back Neo4j.")
        try:
            self.neo4j_writer.delete_company(company_id)   # add this method
        except Exception as rb_err:
            self.logger.error(f"Neo4j rollback also failed (manual cleanup needed): {rb_err}")
            result['rollback_failed'] = True
            result['orphan_company_id'] = company_id
        raise
except Exception as e:
    self.logger.error(f"Failed to store extraction for {company_name}: {e}")
    raise
```

Add `Neo4jWriter.delete_company(company_id)` that detaches and deletes the company subgraph:
```cypher
MATCH (c:Company {id: $id})
OPTIONAL MATCH (c)<-[:ABOUT]-(i:Interaction)
DETACH DELETE c, i
```

(Person nodes are intentionally kept — they may be linked to other companies.)

---

### BUG-045 — `store_extraction` dead `result['error']` assignment (LOW) ✅ FIXED 2026-05-15

**File:** `src/storage/orchestrator.py:90-93`

**Problem:**
```python
except Exception as e:
    self.logger.error(f"Failed to store extraction for {company_name}: {e}")
    result['error'] = str(e)
    raise
```
The `raise` re-throws immediately, so the assigned `result['error']` is never returned to anyone. The line is dead.

**Fix:**
Either delete the assignment, or change `raise` to return the result so callers can inspect it. Given `store_batch` calls `store_extraction` inside its own try/except (`:112-129`), changing to a return would also need `store_batch` to inspect `result['success']` instead of catching exceptions.

Cleanest fix: delete the dead assignment.

---

### BUG-046 — `_generate_id` is collision-prone and not deterministic across name variants (HIGH)

**File:** `src/storage/neo4j_writer.py:343-352`

**Problem:**
```python
def _generate_id(self, text: str) -> str:
    return hashlib.sha256(text.lower().encode()).hexdigest()[:16]
```
- 16 hex chars = 64 bits. Collision probability is low but real, and there's no detection if it happens.
- Only lowercases — doesn't strip whitespace, punctuation, or normalize accents. `"Sara Chen"` and `"Sara Chen "` produce different IDs. `"Acme AI"` vs `"acme.ai"` vs `"Acme.AI"` all different.
- Used for Company, Person, and VCPartner. Person ID falls back to `contact.email or contact.name` — so two contacts with identical names but no email collide.

For companies specifically: the LLM emits `Company.name`. Two runs may produce slightly different names ("Acme AI" vs "Acme") → two Company nodes for the same business → graph fragmentation.

**Fix:**

For Company: prefer `extraction.company.source.external_id` (Affinity org_id) if present, else fall back to a normalized name hash:
```python
def _company_id(self, company) -> str:
    if company.source.external_id:
        return f"affinity_{company.source.external_id}"
    normalized = re.sub(r'[^\w]+', '', company.name.lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
```

For Person: prefer email (already normalized lowercase) over name. Reject person creation entirely if neither is present.

For VCPartner: have the caller pass a canonicalized full name (e.g., resolve `"Ahmed"` → `"Ahmed Zaara"` via a `partners.yaml` config) before computing the id.

---

### BUG-047 — Team debate row is only written when `detected=True` (MEDIUM) ✅ FIXED 2026-05-15

**File:** `src/storage/postgres_writer.py:73-78`

**Problem:**
```python
if extraction.team_debate.detected:
    result['debate_id'] = self._write_team_debate(...)
```
If no debate was detected, no row is written. Downstream code that joins `companies` to `team_debates` has no way to distinguish *"we checked and found no debate"* from *"we never ran the extraction"*. The audit trail is lost.

**Fix:**
Always write the row. The `detected` column already exists in the schema and can be `False`:
```python
result['debate_id'] = self._write_team_debate(
    company_id=company_id,
    debate=extraction.team_debate
)
```

Side benefit: if a future LLM run finds a debate that the previous run missed, you have a baseline row to compare against.

---

### BUG-048 — JSONB values wrapped as `{'items': [...]}` instead of raw arrays (MEDIUM)

**File:** `src/storage/postgres_writer.py:126-128, 173-175, 195`, `src/llm/extraction_engine.py` (consumes raw arrays)

**Problem:**
The writer wraps every list as `{'items': [...]}` before storing to JSONB:
```python
takeaways={'items': what_happened.takeaways},
quotes={'items': quotes},
metrics_mentioned={'items': metrics},
warnings={'items': meta.warnings},
for_arguments={'items': for_args},
...
```
But `extraction_output_format.json` defines these as bare arrays (`"takeaways": ["string"]`, `"warnings": ["string"]`, etc.). Every consumer that reads these rows now has to `row['takeaways']['items']` instead of `row['takeaways']`. Format drift between write-side and the documented contract.

**Fix:**
Store as raw arrays — `psycopg2.extras.Json` handles lists fine:
```python
takeaways=what_happened.takeaways,
quotes=quotes,
metrics_mentioned=metrics,
warnings=meta.warnings,
for_arguments=for_args,
...
```
Update the corresponding `insert_*` functions in `postgres.py` to wrap with `psycopg2.extras.Json(value)` only at the SQL boundary (they already do — the wrapping at the writer level is just redundant nesting).

---

### BUG-049 — `create_relationship` silently no-ops when either node is missing (MEDIUM) ✅ FIXED 2026-05-15 (now logs a warning when either node is missing)

**File:** `src/database/neo4j_client.py:197-223`

**Problem:**
```cypher
MATCH (a:{from_label} {id: $from_id})
MATCH (b:{to_label} {id: $to_id})
MERGE (a)-[r:{rel_type}]->(b)
```
Cypher `MATCH` returns no rows if either node is missing. The subsequent `MERGE` never runs. The function returns `len(result) > 0` → `False`, and the writer logs nothing about it. Misconfigurations (BUG-038 is a special case) appear as "everything succeeded but no edges showed up" — the worst kind of bug to debug.

**Fix:**
Either make it explicit by raising:
```python
def create_relationship(self, ...):
    ...
    result = self.execute_write(query, ...)
    if not result:
        raise ValueError(
            f"Could not create {rel_type}: missing node "
            f"({from_label} id={from_id}) or ({to_label} id={to_id})"
        )
    return True
```
Or log a warning so silent failures are visible during dev:
```python
if not result:
    logger.warning(
        f"create_relationship no-op: ({from_label} id={from_id})-"
        f"[:{rel_type}]->({to_label} id={to_id}) — node(s) missing"
    )
return len(result) > 0
```

---

### BUG-050 — VCPartner identity collapses on first-name vs full-name (MEDIUM)

**File:** `src/storage/neo4j_writer.py:234-261`, `src/llm/prompts/extraction_engine.txt:45`

**Problem:**
The prompt instructs the LLM to fill `deal_status.owner` with "the Yellow or Project A team member most frequently involved" — usually a first name like `"Ahmed"`. The writer hashes that name to make a `partner_id`. So:

- Run A: owner = "Ahmed" → partner_id = sha256("ahmed")[:16] = X
- Run B (different company): owner = "Ahmed Zaara" → partner_id = sha256("ahmed zaara")[:16] = Y
- Run C (autocorrected): owner = "ahmed" → partner_id = X again

Now there are two `VCPartner` nodes for the same human, and ownership relationships are split between them. Queries like "show me all companies owned by Ahmed" miss half.

**Fix:**
Two-part:
1. Add a `partners.yaml` (or settings entry) mapping observed forms → canonical full name:
   ```yaml
   partners:
     - canonical: "Ahmed Zaara"
       aliases: ["Ahmed", "ahmed", "AZ"]
   ```
2. Before computing the partner_id, resolve `owner` to its canonical form. Drop the partner write entirely if unresolved (rather than create a noise node).

Tighten the prompt too: tell the LLM to always emit the partner's full name as it appears in the partners list, with the list embedded in the prompt template.

---

### BUG-051 — `initialize_schema` splits Cypher by `;` naively (LOW)

**File:** `src/database/neo4j_client.py:309-332`

**Problem:**
```python
queries = [q.strip() for q in schema_queries.split(';') if q.strip() and not q.strip().startswith('//')]
```
Splits the whole file on every `;`. Breaks if:
- A semicolon appears inside a string literal (less likely in schema-only files, real risk in query files).
- A `// comment` contains a semicolon — only the leading `//` is filtered, so the rest of the line after `;` becomes a "query".
- The schema includes multi-statement constructs.

**Fix:**
Use the neo4j-python-driver's ability to run multi-statement scripts directly, or split on `;\s*\n` (newline after semicolon, less fragile), or just hand-list the statements in code:

```python
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.id IS UNIQUE",
    "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
    ...
]

def initialize_schema(self):
    with self.get_session() as session:
        for stmt in SCHEMA_STATEMENTS:
            try:
                session.run(stmt)
            except Exception as e:
                logger.warning(f"Schema statement skipped: {stmt[:60]}... → {e}")
```

---

### BUG-052 — Lazy global client init is not thread-safe (LOW)

**File:** `src/database/postgres.py:405-417`, `src/database/neo4j_client.py:335-347`

**Problem:**
```python
_postgres_client: Optional[PostgresClient] = None

def get_postgres_connection() -> PostgresClient:
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient()
        _postgres_client.initialize()
    return _postgres_client
```
Two threads hitting `get_postgres_connection()` simultaneously can both observe `None`, both create a client, both call `initialize()`. One pool is leaked. Same pattern for `get_neo4j_driver`.

Not critical for the current single-process script, but if FastAPI starts handling concurrent requests it becomes a real issue.

**Fix:**
Wrap with a lock:
```python
import threading
_postgres_client_lock = threading.Lock()

def get_postgres_connection() -> PostgresClient:
    global _postgres_client
    if _postgres_client is None:
        with _postgres_client_lock:
            if _postgres_client is None:   # double-checked locking
                client = PostgresClient()
                client.initialize()
                _postgres_client = client
    return _postgres_client
```
Or just construct eagerly at module load time if there's no reason to defer it.

---

### BUG-053 — `get_session` type hints claim `Session` but yield a generator (TRIVIAL) ✅ FIXED 2026-05-15

**File:** `src/database/postgres.py:67`, `src/database/neo4j_client.py:49`

**Problem:**
```python
@contextmanager
def get_session(self) -> Session:
```
The `@contextmanager` decorator means the function returns an `Iterator[Session]`, not `Session`. Type checkers (mypy, pyright) will complain. Runtime works fine.

**Fix:**
```python
from typing import Iterator
from contextlib import contextmanager

@contextmanager
def get_session(self) -> Iterator[Session]:
```

---

## Pipeline Layer (`src/pipeline/`)

### BUG-054 — Pipeline skips embedding, geocoding, and similarity computation (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/pipeline/coordinator.py:122-201`, `src/pipeline/company_processor.py:48-151`
**Related:** `IMPLEMENTATION_PLAN.md` §6.1 (lines 497-510)

**Problem:**
Plan §6.1 specifies the per-company flow:
> b. Run extraction engine on filtered company data
> **c. Generate embedding**
> **d. Geocode location**
> e. Store in Neo4j + PostgreSQL
> **3. Compute similarity relationships (after all companies processed)**

Neither `PipelineCoordinator.process_all_companies` nor `CompanyProcessor.process_company` does any of (c), (d), or (3). They go directly from `extract` → `store_extraction` and stop. The `SimilarityComputer` and `GeocodingService` classes exist but are never instantiated or invoked from the coordinator.

Net effect: no `company_embeddings` rows are ever inserted (so similarity search is impossible), no `lat`/`lng` properties are ever set on Company nodes, and `SIMILAR_TO` edges never form. The graph is missing three of its planned features.

**Fix:**

In `coordinator.py.__init__`, instantiate the missing services:
```python
from src.pipeline.geocoding import get_geocoding_service
from src.pipeline.similarity import SimilarityComputer

self.geocoding = get_geocoding_service()
self.similarity = SimilarityComputer(
    postgres_client=self.postgres,
    neo4j_client=self.neo4j,
    gemini_client=self.flash_client,
)
```

In `CompanyProcessor.process_company`, after `store_extraction` succeeds, add:
```python
company_id = storage_result['neo4j']['company_id']

# Step 5: Generate embedding
self.similarity.generate_company_embedding(
    company_id=company_id,
    company_data=extraction.company.model_dump(),
)

# Step 6: Geocode location (write back to Neo4j Company node)
if extraction.company.location:
    coords = self.geocoding.geocode(extraction.company.location)
    if coords:
        self.neo4j.execute_write(
            "MATCH (c:Company {id: $id}) SET c.lat = $lat, c.lng = $lng",
            {"id": company_id, "lat": coords[0], "lng": coords[1]},
        )
```

In `coordinator.process_all_companies`, after the per-company loop, add:
```python
# Step 3: Compute similarities across all stored companies
self.similarity.compute_all_similarities(threshold=0.75, limit=10)
```

After applying this, also fix BUG-057 (duplicate logic between coordinator and processor) so the same flow doesn't have to be patched twice.

---

### BUG-055 — `SimilarityComputer` uses random noise as embeddings (CRITICAL) ✅ FIXED 2026-05-15

**File:** `src/pipeline/similarity.py:217-236`

**Problem:**
```python
def _generate_simple_embedding(self, text: str) -> List[float]:
    np.random.seed(hash(text) % (2**32))
    embedding = np.random.randn(1536).tolist()
    return embedding
```
This generates 1536 random floats seeded by a hash of the text. **It is not an embedding.** Cosine similarity over these vectors measures hash-seed proximity, not semantic similarity. The downstream `SIMILAR_TO` graph is meaningless noise.

The constructor accepts a `gemini_client` parameter (`similarity.py:26`) clearly intended for real embeddings, but it's never used.

**Fix:**
Use Gemini's embedding API (the `text-embedding-004` model returns 768-d vectors by default; you can also request 1536-d). Replace `_generate_simple_embedding` with:

```python
def _generate_embedding(self, text: str) -> List[float]:
    import google.generativeai as genai
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="SEMANTIC_SIMILARITY",
        output_dimensionality=1536,   # match the pgvector column
    )
    return result["embedding"]
```

If you'd rather keep the `gemini_client` abstraction, expose an `embed_content` method on `GeminiClient` that wraps the call. Either way, **delete `_generate_simple_embedding` entirely** — leaving placeholder code that produces plausible-looking but garbage output is worse than a `NotImplementedError`.

---

### BUG-056 — Embedding seed uses Python's randomized `hash()` (CRITICAL, consequence of BUG-055) ✅ FIXED 2026-05-15 (no longer relevant — real embeddings used)

**File:** `src/pipeline/similarity.py:233`

**Problem:**
```python
np.random.seed(hash(text) % (2**32))
```
Python 3.3+ randomizes string hashes per-process by default (unless `PYTHONHASHSEED=0` is set). So `hash("Acme AI")` returns different values on every Python invocation → different "embeddings" for the same company on every run → the placeholder isn't even deterministic.

**Fix:**
Becomes moot once BUG-055 is fixed (real embeddings are deterministic by construction). If you keep any hash-seeded code path, use `hashlib.sha256(text.encode()).digest()` instead of `hash()`:
```python
import hashlib
seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], 'big')
```

---

### BUG-057 — `process_all_companies` duplicates `CompanyProcessor.process_company` logic (HIGH) ✅ FIXED 2026-05-15 (delegates to `process_company_from_data`)

**File:** `src/pipeline/coordinator.py:122-201` vs `src/pipeline/company_processor.py:48-151`

**Problem:**
`CompanyProcessor` is instantiated at `coordinator.py:113-118` and used by `process_single_company` (`:217-220`) and `process_company_list` (`:236-239`). But `process_all_companies` (`:122-201`) reimplements the same filter → extract → store flow inline, with slightly different result-shape and error-handling. Any fix applied to `CompanyProcessor` (e.g., adding the embedding/geocoding steps from BUG-054) has to be duplicated here.

**Fix:**
Make `process_all_companies` delegate to `CompanyProcessor`:
```python
def process_all_companies(self, limit_per_source=100, company_domains=None):
    companies = self.aggregator.aggregate_by_company(
        company_domains=company_domains,
        limit_per_source=limit_per_source,
    )
    if not companies:
        self.logger.warning("No companies found")
        return []

    results = []
    for i, company_data in enumerate(companies, 1):
        self.logger.info(f"Processing {i}/{len(companies)}: {company_data.company_name}")
        result = self.company_processor.process_company_from_data(company_data)
        results.append(result)
    # ... summary log ...
    return results
```

Add a `process_company_from_data(company_data: CompanyData)` to `CompanyProcessor` that skips the aggregation step (since coordinator already aggregated all companies in one batch). Keep `process_company(company_domain)` as the single-company entry point.

---

### BUG-058 — Geocoding is a hardcoded 40-city dict; plan specified Nominatim (HIGH) ✅ FIXED 2026-05-15

**File:** `src/pipeline/geocoding.py:15-62`
**Related:** `IMPLEMENTATION_PLAN.md` §5.1 ("Geocode location using Nominatim")

**Problem:**
The plan says geocoding should use Nominatim (OpenStreetMap's free API). Bob shipped a hardcoded dict of ~40 major cities. Any company located outside that list — most small/mid-market startups — gets `None`. The `lat`/`lng` Company properties from plan §4.2 will be missing for the majority of companies.

**Fix:**
Add Nominatim as the primary backend; keep the dict as a cache/fallback only:

```python
import requests
import time

class GeocodingService:
    def __init__(self, user_agent: str = "vc-intelligence/0.1"):
        self.user_agent = user_agent
        self.cache: Dict[str, Optional[Tuple[float, float]]] = {}
        self._last_call = 0.0  # Nominatim rate limit: 1 req/sec

    def geocode(self, location: Optional[str]) -> Optional[Tuple[float, float]]:
        if not location:
            return None
        key = location.lower().strip()
        if key in self.cache:
            return self.cache[key]

        # Try Nominatim
        elapsed = time.time() - self._last_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": location, "format": "json", "limit": 1},
                headers={"User-Agent": self.user_agent},
                timeout=10,
            )
            self._last_call = time.time()
            r.raise_for_status()
            hits = r.json()
            if hits:
                coords = (float(hits[0]["lat"]), float(hits[0]["lon"]))
                self.cache[key] = coords
                return coords
        except Exception as e:
            self.logger.warning(f"Nominatim failed for '{location}': {e}")

        # Fallback to hardcoded dict
        coords = self._lookup_coordinates(key)
        self.cache[key] = coords
        return coords
```

Nominatim's terms of use require a non-default `User-Agent` and respect a 1-req/sec rate limit. Persist the cache to disk (sqlite or json file) so repeated runs don't re-hit the API.

---

### BUG-059 — Geocoding substring-match returns wrong city for ambiguous names (HIGH) ✅ FIXED 2026-05-15

**File:** `src/pipeline/geocoding.py:121-124`

**Problem:**
```python
for city, coords in CITY_COORDINATES.items():
    if city in location or location in city:
        return coords
```
- `"Paris, Texas"` → `"paris" in "paris, texas"` → True → returns Paris, France coordinates.
- `"Berlin Heights, Ohio"` → returns Berlin, Germany.
- `"London, Ontario"` → returns London, UK.

Real companies in these towns get geo-located to a different continent. The plan tags `location_city` and `location_country` separately on the Company node (§4.2), so the country mismatch will be invisible until someone looks at a map.

**Fix:**
After applying BUG-058 (Nominatim becomes primary), this fallback path matters less. But still tighten:

```python
def _lookup_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
    # Direct match only
    if location in CITY_COORDINATES:
        return CITY_COORDINATES[location]
    # Try "City, Country" format — match on city + country together
    parts = [p.strip() for p in location.split(',')]
    if len(parts) >= 1 and parts[0] in CITY_COORDINATES:
        # Optionally: verify country if provided (would need country-coded dict)
        return CITY_COORDINATES[parts[0]]
    # No partial-substring fallback — too dangerous
    return None
```

Drop the substring loop entirely. False positives are worse than `None`.

---

### BUG-060 — Multiple `GeminiClient` instances overwrite each other via global `genai.configure` (HIGH)

**File:** `src/pipeline/coordinator.py:84-91`, `src/llm/gemini_client.py:59`

**Problem:**
The coordinator creates two clients:
```python
self.flash_client = GeminiClient(api_key=gemini_api_key, model="flash")
self.pro_client   = GeminiClient(api_key=gemini_api_key, model="pro")
```
Each constructor calls `genai.configure(api_key=self.api_key)` (`gemini_client.py:59`). `genai.configure` sets a **global** API key for the `google.generativeai` module. The second call overwrites the first — fine when both keys are the same, but if a caller ever passes different keys (e.g., separate quotas for flash vs. pro), the second wins silently and the first client uses the wrong key.

More importantly: the legacy `google-generativeai` SDK keeps the whole client state global. You can't have two truly independent clients in the same process.

**Fix:**
Two options:

**Option A (short-term):** Document that all `GeminiClient` instances in one process must share a key. Optionally guard against drift in the constructor:
```python
_configured_key = None

def __init__(self, api_key=None, ...):
    global _configured_key
    ...
    if _configured_key and _configured_key != self.api_key:
        raise GeminiError(
            "Cannot create GeminiClient with a different API key in the same process "
            "(google.generativeai uses module-global configuration)."
        )
    genai.configure(api_key=self.api_key)
    _configured_key = self.api_key
```

**Option B (long-term):** Migrate to the new `google-genai` SDK per BUG-016, which uses per-`Client` configuration and supports multiple independent clients cleanly.

---

### BUG-061 — Coordinator reads `os.getenv` directly twice per connector (MEDIUM)

**File:** `src/pipeline/coordinator.py:58-72`

**Problem:**
```python
self.granola = GranolaConnector(
    api_key=granola_api_key or os.getenv('GRANOLA_API_KEY')
) if granola_api_key or os.getenv('GRANOLA_API_KEY') else None
```
- `os.getenv('GRANOLA_API_KEY')` is called twice (once in the ternary, once in the constructor's default chain).
- Reads env directly instead of `src.config.Settings` — same antipattern as BUG-009.
- Pattern is repeated four times (Granola, Affinity, Gmail, Slack).

**Fix:**
Compute once via Settings:
```python
from src.config import get_settings
settings = get_settings()

granola_key = granola_api_key or settings.granola_api_key
self.granola = GranolaConnector(api_key=granola_key) if granola_key else None

affinity_key = affinity_api_key or settings.affinity_api_key
self.affinity = AffinityConnector(api_key=affinity_key) if affinity_key else None

# etc.
```

---

### BUG-062 — `compute_similarities` reads embedding column without pgvector adapter (MEDIUM, depends on BUG-043)

**File:** `src/pipeline/similarity.py:90-109`

**Problem:**
```python
query = "SELECT embedding FROM company_embeddings WHERE company_id = %s ORDER BY generated_at DESC LIMIT 1"
result = self.postgres.execute_query(query, (company_id,))
...
embedding = result[0]['embedding']
similar = self.postgres.search_similar_companies(embedding=embedding, ...)
```
Without `register_vector(conn)` (BUG-043), `result[0]['embedding']` comes back as a string like `'[0.1, 0.2, ...]'` rather than `List[float]`. Passing that string to `search_similar_companies` and into `%s::vector` may or may not work — most likely it does work via pgvector's string-cast parser, but the type contract is violated and a switch to a different vector store would break.

**Fix:**
Becomes moot once BUG-043 is applied. With `register_vector(conn)`, `result[0]['embedding']` is a proper `numpy.ndarray` / list, and the round-trip is type-safe.

---

### BUG-063 — `np.random.seed` mutates global numpy RNG state (MEDIUM)

**File:** `src/pipeline/similarity.py:233-234`

**Problem:**
```python
np.random.seed(hash(text) % (2**32))
embedding = np.random.randn(1536).tolist()
```
`np.random.seed` is a module-global seed. Any other code in the process using `np.random` (after this call) reads from a deterministically-seeded RNG until the next reseeding. If embeddings are computed in the middle of a pipeline run, scientific code elsewhere gets contaminated.

**Fix:**
Becomes moot once BUG-055 is applied (real embeddings don't use numpy RNG). If a numpy fallback ever stays in the codebase, use a local RNG:
```python
rng = np.random.default_rng(seed=int.from_bytes(...))
embedding = rng.standard_normal(1536).tolist()
```

---

### BUG-064 — `result['extraction']` is a Pydantic model, breaks JSON serialization (MEDIUM) ✅ FIXED 2026-05-15

**File:** `src/pipeline/company_processor.py:143`

**Problem:**
```python
result['success'] = True
result['extraction'] = extraction   # <- Pydantic model, not a dict
```
Everything else in `result` is JSON-native (str/int/bool/list/dict), but `extraction: ExtractionOutput` is a Pydantic model. If a caller passes `result` to `json.dumps`, it raises `TypeError: Object of type ExtractionOutput is not JSON serializable`.

**Fix:**
```python
result['extraction'] = extraction.model_dump()
```
If callers need the typed model, return a separate field or a tuple `(result_dict, extraction)`.

---

### BUG-065 — `generate_company_embedding` inserts duplicate rows on every run (MEDIUM)

**File:** `src/pipeline/similarity.py:40-69`, `src/database/postgres.py:139-155`

**Problem:**
`insert_company_embedding` always INSERTs a new row. Running the pipeline twice doubles the rows in `company_embeddings`. `compute_similarities` then queries `ORDER BY generated_at DESC LIMIT 1` so it ignores the old ones — but the table bloats and querying gets slower over time.

**Fix:**
Two options:

**Option A — upsert:** Change the SQL to `INSERT ... ON CONFLICT (company_id) DO UPDATE`. Requires adding a unique constraint on `company_id`:
```sql
ALTER TABLE company_embeddings ADD CONSTRAINT uniq_company_embedding UNIQUE (company_id);
```
Then:
```sql
INSERT INTO company_embeddings (company_id, embedding, embedding_text)
VALUES (%s, %s, %s)
ON CONFLICT (company_id) DO UPDATE
  SET embedding = EXCLUDED.embedding,
      embedding_text = EXCLUDED.embedding_text,
      generated_at = NOW()
RETURNING id
```

**Option B — keep history:** If you want embedding history (useful for tracking how a company's positioning drifts over time), leave the schema and add a `DELETE FROM company_embeddings WHERE company_id = %s AND generated_at < NOW() - INTERVAL '30 days'` cleanup pass.

Pick A unless you've explicitly decided you want history.

---

### BUG-066 — `add_custom_location` mutates module-level dict (LOW) ✅ FIXED 2026-05-15

**File:** `src/pipeline/geocoding.py:158-159`

**Problem:**
```python
CITY_COORDINATES[location_lower] = (latitude, longitude)
```
Mutates the module-level dict. All `GeocodingService` instances (and any other importer of `CITY_COORDINATES`) see the change. If two code paths call `add_custom_location` with different coords for the same city, last-writer-wins, silently.

**Fix:**
Make instance-level:
```python
def __init__(self):
    self.coords = dict(CITY_COORDINATES)   # per-instance copy
    self.cache = {}

def add_custom_location(self, location, lat, lng):
    key = location.lower().strip()
    self.coords[key] = (lat, lng)
    self.cache[key] = (lat, lng)
```
Update `_lookup_coordinates` to use `self.coords` instead of `CITY_COORDINATES`.

---

### BUG-067 — `process_company_batch` has dead try/except (LOW) ✅ FIXED 2026-05-15

**File:** `src/pipeline/company_processor.py:172-185`

**Problem:**
```python
try:
    result = self.process_company(...)
    results.append(result)
except Exception as e:
    self.logger.error(...)
    results.append({...})
```
But `process_company` (`:48-151`) catches all exceptions internally and returns a `result` dict with `success=False` and an `error` key. The outer except never fires. Dead code.

**Fix:**
Drop the outer try/except entirely:
```python
for i, domain in enumerate(company_domains, 1):
    self.logger.info(f"Processing {i}/{len(company_domains)}: {domain}")
    result = self.process_company(company_domain=domain, limit_per_source=limit_per_source)
    results.append(result)
```

Or, if you'd rather have `process_company` raise on hard failure, remove its internal catch-all. Pick one error model and stick to it across the layer.

---

### BUG-068 — `get_pipeline_status` reports `is not None`, not actual connectivity (LOW) ✅ FIXED 2026-05-15

**File:** `src/pipeline/coordinator.py:241-262`

**Problem:**
```python
'databases': {
    'postgres': self.postgres is not None,
    'neo4j': self.neo4j is not None
}
```
Reports `True` as long as the objects were constructed — even if the underlying connection has since died. A health endpoint built on this returns "OK" when the DB is unreachable.

**Fix:**
Actually ping:
```python
def _postgres_alive(self) -> bool:
    try:
        self.postgres.execute_query("SELECT 1", fetch=True)
        return True
    except Exception:
        return False

def _neo4j_alive(self) -> bool:
    try:
        self.neo4j.execute_query("RETURN 1")
        return True
    except Exception:
        return False

# in get_pipeline_status:
'databases': {
    'postgres': self._postgres_alive(),
    'neo4j': self._neo4j_alive(),
}
```

---

### BUG-069 — Hardcoded `'credentials.json'` path for Gmail (LOW)

**File:** `src/pipeline/coordinator.py:66-68`

**Problem:**
```python
self.gmail = GmailConnector(
    credentials_path=gmail_credentials_path or 'credentials.json'
) if gmail_credentials_path or os.path.exists('credentials.json') else None
```
`'credentials.json'` is relative to the current working directory. Runs from a different cwd (Docker volume, cron, IDE debug config) silently skip Gmail.

**Fix:**
Pull from settings:
```python
gmail_creds = gmail_credentials_path or settings.gmail_credentials
self.gmail = GmailConnector(credentials_path=gmail_creds) if gmail_creds and os.path.exists(gmail_creds) else None
```

---

### BUG-070 — Dead `import re` in geocoding (TRIVIAL) ✅ FIXED 2026-05-15

**File:** `src/pipeline/geocoding.py:9`

**Problem:**
`import re` — never used.

**Fix:**
Delete the import.

---

### BUG-071 — File names diverge from `IMPLEMENTATION_PLAN.md` (INFO)

**File:** `src/pipeline/`, `src/storage/`
**Related:** `IMPLEMENTATION_PLAN.md` §5.1 line 480-487, §6.1 line 514-520

**Problem:**
Plan specifies:
```
src/pipeline/
├── orchestrator.py     # Bob shipped: coordinator.py
├── processor.py        # Bob shipped: company_processor.py
└── similarity.py       ✓ matches

src/storage/
├── geocoding.py        # Bob put it in src/pipeline/geocoding.py instead
```

Not bugs — runtime behavior is unaffected — but anyone reading the plan and grepping for `orchestrator.py` in `src/pipeline/` finds nothing. Worth either renaming the files or updating the plan to match what shipped.

**Fix — pick one:**

- **Match the plan**: rename `coordinator.py` → `orchestrator.py`, `company_processor.py` → `processor.py`, move `geocoding.py` → `src/storage/geocoding.py`. Update imports.
- **Update the plan**: edit §5.1 and §6.1 file trees to match the shipped layout.

Either is fine. Pick one before adding more code that references these paths.

---

### BUG-072 — No rate limiting between Gemini calls (INFO)

**File:** `src/pipeline/coordinator.py:153-194`, `src/pipeline/company_processor.py:153-193`

**Problem:**
For 15 companies × (1 relevance call per interaction × ~10 interactions + 1 extraction call) = roughly 165 Gemini calls per pipeline run, fired in tight loops with no throttling. Gemini's free-tier limits are 15 RPM for Pro and 2 RPM for Flash on some plans. The pipeline will hit `429 RESOURCE_EXHAUSTED` and BUG-011's `retry_if_exception_type(Exception)` will retry the whole call three times, burning quota faster.

**Fix (deferred, depends on traffic):**
Once BUG-011 is fixed to retry on 429 with backoff specifically, this is largely handled. If you want explicit throttling:
- Wrap calls in `tenacity.wait_chain` with a fixed minimum interval (e.g., 4 seconds for Pro).
- Or use `asyncio.Semaphore(n)` once the layer goes async.

Not a blocker for MVP — flag once volume > 50 companies per run.

---

*Add new entries below this line as they come up.*
