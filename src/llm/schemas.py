"""Pydantic schemas for LLM extraction output

These models match extraction_output_format.json exactly and are used to:
1. Validate LLM extraction output
2. Provide type hints for extraction engine
3. Serialize to JSON for database storage
"""

import re
from typing import List, Optional, Literal, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Format validators (BUG-031). Permissive: empty / None pass through.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$"
)


def _validate_date(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not _ISO_DATE_RE.match(v):
        raise ValueError(f"Expected YYYY-MM-DD, got '{v}'")
    return v


def _validate_datetime(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    # Lenient: accept date-only ("2025-09-22") and promote to datetime.
    if _ISO_DATE_RE.match(v):
        return f"{v}T00:00:00Z"
    if not _ISO_DATETIME_RE.match(v):
        raise ValueError(f"Expected ISO 8601 datetime, got '{v}'")
    return v


# ---------------------------------------------------------------------------
# LLM drift-tolerance helpers — used by mode="before" field validators.
# All helpers are no-ops for already-correct shapes; they only intervene when
# the LLM emits something off-schema.
# ---------------------------------------------------------------------------

# Keys we accept as the "primary string" when the LLM wraps a string in a dict.
_STR_KEYS = ("name", "text", "value", "label", "tag", "description", "title")


def _coerce_str_list(v: Any) -> Any:
    """Normalize a value into a List[str], tolerating object items.

    Accepts:
      - List[str]         -> kept (empties stripped)
      - List[dict]        -> unwrapped via _STR_KEYS
      - List[None]        -> dropped
      - non-list          -> returned unchanged (Pydantic will reject)
    """
    if not isinstance(v, list):
        return v
    out: List[str] = []
    for item in v:
        if item is None:
            continue
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                out.append(stripped)
        elif isinstance(item, dict):
            for key in _STR_KEYS:
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    break
        else:
            out.append(str(item))
    return out


_CURRENCY_RE = re.compile(
    r"""^\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kmbKMB]|million|billion|thousand)?\s*$""",
    re.IGNORECASE,
)
_CURRENCY_MULT = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}


def _coerce_currency(v: Any) -> Any:
    """Accept '$5M', '5 million', '5,000,000', or a plain number — emit float."""
    if v is None or isinstance(v, (int, float)):
        return v
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    m = _CURRENCY_RE.match(s)
    if not m:
        return None  # Don't fail — drop silently.
    amount = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").lower()
    return amount * _CURRENCY_MULT.get(suffix, 1)


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")


def _coerce_int_loose(v: Any) -> Any:
    """Accept '30 minutes' / '30' / 30 — emit int or None."""
    if v is None or isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if not isinstance(v, str):
        return v
    m = _DURATION_RE.match(v)
    return int(float(m.group(1))) if m else None


# ---------------------------------------------------------------------------
# Enum synonym maps — map free-form LLM values to canonical Literals so we
# capture the LLM's *intent* instead of silently overwriting with a default.
#
# Each map is {canonical_value: [substring_aliases_lowercased]}.
# `_resolve_enum` checks canonical (exact, case-insensitive) first, then
# falls through to a substring match against the aliases. First hit wins —
# alias lists are ordered most-specific → least-specific.
# ---------------------------------------------------------------------------

STAGE_SYNONYMS = {
    "Pre-seed": ["pre-seed", "preseed", "pre seed", "angel round"],
    "Seed": ["seed"],
    "Series A": ["series a", "a-round", "a round"],
    "Series B": ["series b", "b-round", "b round"],
    "Series C+": ["series c", "series d", "series e", "series f", "series c+"],
    "Growth": ["growth", "late-stage", "late stage", "pre-ipo", "pre ipo", "mature"],
}

MOMENTUM_SYNONYMS = {
    "accelerating": ["accelerat", "ramping", "hot", "trending up", "picking up", "growing fast", "momentum building"],
    "stable": ["stable", "steady", "consistent", "even", "flat", "ongoing", "tracking to plan"],
    "stalling": ["stall", "slow", "cooling", "losing", "declining", "fading", "cooling off"],
    "dead": ["dead", "killed", "rejected", "no longer", "cold", "lost", "passed on"],
}

PIPELINE_STAGE_SYNONYMS = {
    "Tracking": ["tracking", "watching", "monitor", "initial track", "scouting"],
    "First call": ["first call", "first meeting", "intro", "introduction", "kickoff", "kick off", "initial call"],
    "Diligence": ["diligence", "due diligence", "dd", "deep dive", "evaluat", "review", "examining"],
    "IC review": ["ic review", "investment committee", "partner meeting", "ic-review"],
    "Decision": ["decision", "decided", "closed", "term sheet", "tsr", "verdict reached", "closed-won", "closed-lost"],
}

VERDICT_SYNONYMS = {
    "tracking": ["track", "watch", "monitor", "consider", "interested", "early", "in pipeline", "follow"],
    "diligence": ["diligence", "dd", "evaluat", "deep dive", "examining", "reviewing"],
    "invested": ["invested", "closed", "closed-won", "fund", "wire sent", "term sheet sign", "signed", "in portfolio", "yes"],
    "passed": ["pass", "declined", "rejected", "no fit", "no go", "dead", "closed-lost", "not a fit"],
}

ROLE_SYNONYMS = {
    "Founder": ["founder", "co-founder", "cofounder", "founding"],
    "CEO": ["ceo", "chief executive", "president"],
    "CTO": ["cto", "chief technology", "chief technical", "head of engineering", "vp engineering"],
    "COO": ["coo", "chief operating", "chief operations"],
    "Investor": ["investor", "vc", "venture capital", "angel", "lp ", " lp", "limited partner", "gp ", " gp"],
    "Operator": ["operator", "engineer", "designer", "product manager", "developer", "manager", "head of", "vp", "director", "lead", "marketing", "sales", "growth", "ops"],
}

SENTIMENT_SYNONYMS = {
    "positive": ["very positive", "positive", "good", "great", "excellent", "amazing", "strong", "favorable", "enthusiast", "promising", "exciting", "optimist", "love", "impressed", "bullish"],
    "negative": ["very negative", "negative", "bad", "poor", "weak", "concern", "skeptic", "doubt", "worry", "cautious", "unfavorable", "concerning", "bearish", "red flag"],
    "neutral": ["neutral", "mixed", "balanced", "moderate", "ok", "fine", "average", "unclear"],
}

CHANNEL_SYNONYMS = {
    "video": ["zoom", "google meet", "google-meet", "google_meet", "g-meet", "ms teams", "microsoft teams", "teams call", "webex", "video call", "videoconference", "videocall", "online", "virtual", "video", "facetime"],
    "in_person": ["in person", "in-person", "onsite", "on-site", "office", "face-to-face", "face to face", "f2f", "irl"],
    "phone": ["phone", "telephone", "voice call", "phone call", "voice-only"],
    "email": ["email", "e-mail", "gmail thread", "outlook"],
    "slack": ["slack", "discord", "chat thread"],
}

INTERACTION_TYPE_SYNONYMS = {
    "intro_meeting": ["intro meeting", "intro", "introduction", "first call", "first meeting", "kickoff", "kick off", "initial call", "initial meeting"],
    "deep_dive": ["deep dive", "deep-dive", "follow up", "follow-up", "technical review", "diligence call", "dd call", "second meeting"],
    "demo": ["demo", "demonstration", "product walkthrough", "product walk-through", "showcase", "live demo"],
    "reference_call": ["reference", "customer reference", "customer call", "ref call"],
    "email": ["email", "e-mail", "mail thread"],
    "slack_message": ["slack", "chat", "dm "],
    "memo": ["memo", "writeup", "write-up", "internal doc", "investment memo"],
    "ic_review": ["ic review", "investment committee", "partner meeting", "ic-review"],
}

METRIC_LABEL_SYNONYMS = {
    "ARR": ["arr", "annual recurring revenue", "annual revenue"],
    "MRR": ["mrr", "monthly recurring revenue", "monthly revenue"],
    "customers": ["customer", "logo", "account", "client count", "paying user"],
    "burn": ["burn", "cash burn", "monthly burn", "spend rate"],
    "runway": ["runway", "months of cash", "cash runway"],
    "growth_rate": ["growth", "mom", "yoy", "qoq", "growth rate", "monthly growth", "year over year"],
    "margin": ["margin", "gross margin", "net margin", "profit margin"],
    "headcount": ["headcount", "team size", "employee count", "fte", "staff size", "team of"],
}

SOURCE_TYPE_SYNONYMS = {
    "granola": ["granola", "meeting note", "meeting transcript"],
    "affinity": ["affinity", "crm"],
    "slack": ["slack"],
    "gmail": ["gmail", "email", "mail"],
}


def _resolve_enum(
    value: Any,
    synonyms: dict,
    fallback: Any,
) -> Any:
    """Match `value` against a canonical enum with synonym fallback.

    Returns the canonical key if matched; otherwise `fallback`. Pass-through
    for None, empty string, and non-string types so Pydantic can run its
    own checks on already-correct shapes.
    """
    if value is None:
        return fallback
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return fallback
    # 1. Case-insensitive exact match against canonical keys.
    for canonical in synonyms:
        if s.lower() == canonical.lower():
            return canonical
    # 2. Substring match against aliases.
    s_lower = s.lower()
    for canonical, aliases in synonyms.items():
        for alias in aliases:
            if alias in s_lower:
                return canonical
    return fallback


# ============================================
# COMPANY BLOCK
# ============================================

class CompanySource(BaseModel):
    """Company data source tracking"""
    types: List[Literal["granola", "affinity", "slack", "gmail"]] = Field(default_factory=list)
    external_id: Optional[str] = None

    @field_validator("types", mode="before")
    @classmethod
    def _coerce_types(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return v
        out = []
        for item in v:
            resolved = _resolve_enum(item, SOURCE_TYPE_SYNONYMS, None)
            if resolved and resolved not in out:
                out.append(resolved)
        return out


class Company(BaseModel):
    """Company profile extracted from interactions"""
    id: Optional[str] = Field(None, description="Assigned by the database on insert; null in LLM output")
    name: str = Field(min_length=1, description="Exact company name as written by founders")
    one_liner: Optional[str] = Field(None, description="One crisp sentence describing what the company does (max 15 words)")
    sector: Optional[str] = Field(None, description="Specific sector, e.g. 'AI Infrastructure' not just 'AI'")
    stage: Optional[Literal["Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Growth"]] = None
    location: Optional[str] = Field(None, description="'City, Country' format from any mention in interactions")
    website: Optional[str] = Field(None, description="Full URL with https://, derived from founder emails or explicit mentions")
    tags: List[str] = Field(default_factory=list, description="3-6 short categorization tags")
    first_met_at: Optional[str] = Field(None, description="YYYY-MM-DD; date of earliest interaction")
    key_strengths: List[str] = Field(default_factory=list, description="3-6 distinct strengths across interactions")
    key_concerns: List[str] = Field(default_factory=list, description="2-5 distinct concerns across interactions")
    deal_momentum: Optional[Literal["accelerating", "stable", "stalling", "dead"]] = Field(
        None, description="Trajectory based on interaction cadence and sentiment"
    )
    source: Optional[CompanySource] = None

    @field_validator("first_met_at")
    @classmethod
    def _validate_first_met(cls, v: Optional[str]) -> Optional[str]:
        return _validate_date(v)

    @field_validator("stage", mode="before")
    @classmethod
    def _coerce_stage(cls, v: Any) -> Any:
        return _resolve_enum(v, STAGE_SYNONYMS, None)

    @field_validator("deal_momentum", mode="before")
    @classmethod
    def _coerce_momentum(cls, v: Any) -> Any:
        return _resolve_enum(v, MOMENTUM_SYNONYMS, None)

    @field_validator("tags", "key_strengths", "key_concerns", mode="before")
    @classmethod
    def _coerce_string_lists(cls, v: Any) -> Any:
        return _coerce_str_list(v)


# ============================================
# DEAL STATUS BLOCK
# ============================================

class DealStatus(BaseModel):
    """Current deal pipeline status"""
    pipeline_stage: Literal["Tracking", "First call", "Diligence", "IC review", "Decision"] = "Tracking"
    # Lenient: cross-block validator backfills from interactions if missing.
    last_touch_at: Optional[str] = None
    next_step: Optional[str] = None
    owner: Optional[str] = None

    @field_validator("pipeline_stage", mode="before")
    @classmethod
    def _coerce_stage(cls, v: Any) -> Any:
        return _resolve_enum(v, PIPELINE_STAGE_SYNONYMS, "Tracking")

    @field_validator("last_touch_at")
    @classmethod
    def _v_last_touch(cls, v: Optional[str]) -> Optional[str]:
        # Permissive: cross-block validator backfills from interactions.
        return _validate_datetime(v)


# ============================================
# CONTACTS BLOCK
# ============================================

class Contact(BaseModel):
    """External contact (founder, reference, etc.)"""
    name: str
    role: Literal["Founder", "CEO", "CTO", "COO", "Investor", "Operator", "Other"]
    is_primary: bool = False
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("role", mode="before")
    @classmethod
    def _coerce_role(cls, v: Any) -> Any:
        return _resolve_enum(v, ROLE_SYNONYMS, "Other")


# ============================================
# INTERACTIONS BLOCK
# ============================================

class InteractionSource(BaseModel):
    """Interaction source tracking"""
    type: Optional[Literal["granola", "affinity", "slack", "gmail"]] = None
    url: Optional[str] = None
    external_id: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_source_type(cls, v: Any) -> Any:
        return _resolve_enum(v, SOURCE_TYPE_SYNONYMS, None)


class MetricMention(BaseModel):
    """Metric mentioned in interaction"""
    label: Literal["ARR", "MRR", "customers", "burn", "runway", "growth_rate", "margin", "headcount", "other"]
    value: str
    as_of: Optional[str] = None  # YYYY-MM-DD

    @field_validator("label", mode="before")
    @classmethod
    def _coerce_label(cls, v: Any) -> Any:
        return _resolve_enum(v, METRIC_LABEL_SYNONYMS, "other")

    @field_validator("as_of")
    @classmethod
    def _v_as_of(cls, v: Optional[str]) -> Optional[str]:
        return _validate_date(v)


class Quote(BaseModel):
    """Direct quote from interaction"""
    speaker: str
    text: str


class WhatHappened(BaseModel):
    """Detailed interaction content"""
    summary: str
    takeaways: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    metrics_mentioned: List[MetricMention] = Field(default_factory=list)
    quotes: List[Quote] = Field(default_factory=list)

    @field_validator("metrics_mentioned", mode="before")
    @classmethod
    def _coerce_metrics(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                label = _resolve_enum(item, METRIC_LABEL_SYNONYMS, "other")
                result.append({"label": label, "value": item, "as_of": None})
            else:
                result.append(item)
        return result

    @field_validator("quotes", mode="before")
    @classmethod
    def _coerce_quotes(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return v
        return [
            {"speaker": "unknown", "text": item} if isinstance(item, str) else item
            for item in v
        ]

    @field_validator("takeaways", "topics", mode="before")
    @classmethod
    def _coerce_takeaways_topics(cls, v: Any) -> Any:
        return _coerce_str_list(v)


class Interaction(BaseModel):
    """Single interaction (meeting, email, message, etc.)"""
    id: str
    type: Literal["intro_meeting", "deep_dive", "demo", "reference_call", "email", "slack_message", "memo", "ic_review", "other"]
    title: str
    subtitle: Optional[str] = None
    occurred_at: str  # ISO 8601 datetime
    duration_minutes: Optional[int] = None
    channel: Literal["video", "in_person", "phone", "email", "slack", "other"]
    sentiment: Literal["positive", "neutral", "negative"]
    participants: List[str] = Field(default_factory=list)
    source: Optional[InteractionSource] = None
    what_happened: WhatHappened

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> Any:
        return _resolve_enum(v, INTERACTION_TYPE_SYNONYMS, "other")

    @field_validator("channel", mode="before")
    @classmethod
    def _coerce_channel(cls, v: Any) -> Any:
        return _resolve_enum(v, CHANNEL_SYNONYMS, "other")

    @field_validator("sentiment", mode="before")
    @classmethod
    def _coerce_sentiment(cls, v: Any) -> Any:
        return _resolve_enum(v, SENTIMENT_SYNONYMS, "neutral")

    @field_validator("participants", mode="before")
    @classmethod
    def _coerce_participants(cls, v: Any) -> Any:
        """Accept either plain strings or objects with a `name` field."""
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("display_name") or ""
                if name:
                    result.append(name)
        return result

    @field_validator("occurred_at")
    @classmethod
    def _v_occurred_at(cls, v: str) -> str:
        validated = _validate_datetime(v)
        if validated is None:
            raise ValueError("occurred_at is required")
        return validated

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def _coerce_duration(cls, v: Any) -> Any:
        return _coerce_int_loose(v)


# ============================================
# TEAM DEBATE BLOCK
# ============================================

class Argument(BaseModel):
    """Argument for or against investing"""
    argument: str
    supporter: Optional[str] = None
    evidence: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_alias_keys(cls, data: Any) -> Any:
        """LLM sometimes emits {text|statement|description|claim: ...} instead
        of {argument: ...}. Map any of those onto `argument`."""
        if not isinstance(data, dict):
            return data
        if data.get("argument"):
            return data
        for alias in ("text", "statement", "description", "claim", "point", "rationale"):
            val = data.get(alias)
            if isinstance(val, str) and val.strip():
                data = {**data, "argument": val.strip()}
                break
        return data


class TeamDebate(BaseModel):
    """Internal team debate about the deal"""
    detected: bool = False
    for_arguments: List[Argument] = Field(default_factory=list)
    against_arguments: List[Argument] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)

    @field_validator("for_arguments", "against_arguments", mode="before")
    @classmethod
    def _coerce_argument_list(cls, v: Any) -> Any:
        """LLMs sometimes emit `[\"Strong PMF\", ...]` instead of
        `[{\"argument\": \"Strong PMF\"}, ...]`. Wrap bare strings into the
        Argument shape so a minor schema-drift doesn't fail extraction.
        """
        if not isinstance(v, list):
            return v
        coerced: List[Any] = []
        for item in v:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    coerced.append({"argument": stripped})
            elif item is None:
                continue
            else:
                coerced.append(item)
        return coerced

    @field_validator("open_questions", mode="before")
    @classmethod
    def _coerce_open_questions(cls, v: Any) -> Any:
        return _coerce_str_list(v)


# ============================================
# DECISION RECORD BLOCK
# ============================================

class DecisionRecord(BaseModel):
    """Investment decision record"""
    verdict: Literal["tracking", "diligence", "invested", "passed"]
    decided_at: Optional[str] = None  # ISO 8601 datetime
    rationale: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)
    check_size: Optional[str] = None
    valuation: Optional[str] = None

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v: Any) -> Any:
        return _resolve_enum(v, VERDICT_SYNONYMS, "tracking")

    @field_validator("decided_at")
    @classmethod
    def _v_decided_at(cls, v: Optional[str]) -> Optional[str]:
        return _validate_datetime(v)

    @field_validator("conditions", mode="before")
    @classmethod
    def _coerce_conditions(cls, v: Any) -> Any:
        return _coerce_str_list(v)


# ============================================
# COMPANY NOW BLOCK (populated by query engine)
# ============================================

class Funding(BaseModel):
    """Company funding information"""
    last_round_stage: Optional[str] = None
    last_round_amount_usd: Optional[float] = None
    total_raised_usd: Optional[float] = None

    @field_validator("last_round_amount_usd", "total_raised_usd", mode="before")
    @classmethod
    def _coerce_amount(cls, v: Any) -> Any:
        return _coerce_currency(v)


class NewsItem(BaseModel):
    """News article about company"""
    headline: str
    url: str
    published_at: str  # YYYY-MM-DD
    source: str

    @field_validator("published_at")
    @classmethod
    def _v_pub(cls, v: str) -> str:
        validated = _validate_date(v)
        if validated is None:
            raise ValueError("published_at is required")
        return validated


class Signal(BaseModel):
    """Growth or traction signal"""
    label: str
    detected_at: str  # YYYY-MM-DD

    @field_validator("detected_at")
    @classmethod
    def _v_detected(cls, v: str) -> str:
        validated = _validate_date(v)
        if validated is None:
            raise ValueError("detected_at is required")
        return validated


class CompanyNow(BaseModel):
    """Current company data (populated by query engine, not LLM)"""
    domain: Optional[str] = None
    fetched_at: Optional[str] = None  # ISO 8601 datetime
    headcount: Optional[int] = None
    open_roles: Optional[int] = None
    funding: Funding = Field(default_factory=Funding)
    latest_news: List[NewsItem] = Field(default_factory=list)
    signals: List[Signal] = Field(default_factory=list)

    @field_validator("fetched_at")
    @classmethod
    def _v_fetched_at(cls, v: Optional[str]) -> Optional[str]:
        return _validate_datetime(v)

    @field_validator("funding", mode="before")
    @classmethod
    def _coerce_funding(cls, v: Any) -> Any:
        """Accept null/missing funding and substitute an empty Funding object."""
        return v if v is not None else {}

    @field_validator("latest_news", "signals", mode="before")
    @classmethod
    def _coerce_null_lists(cls, v: Any) -> Any:
        return v if v is not None else []


# ============================================
# EXTRACTION META BLOCK
# ============================================

class ExtractionMeta(BaseModel):
    """Extraction metadata"""
    model: str
    extracted_at: str  # ISO 8601 datetime
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)

    @field_validator("extracted_at")
    @classmethod
    def _v_extracted_at(cls, v: str) -> str:
        validated = _validate_datetime(v)
        if validated is None:
            raise ValueError("extracted_at is required")
        return validated

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: Any) -> Any:
        """LLM sometimes emits 0–100 instead of 0–1. Clamp to [0,1]."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.5
        if f > 1.0:
            f = f / 100.0
        return max(0.0, min(1.0, f))

    @field_validator("warnings", mode="before")
    @classmethod
    def _coerce_warnings(cls, v: Any) -> Any:
        return _coerce_str_list(v)


# ============================================
# COMPLETE EXTRACTION OUTPUT
# ============================================

class ExtractionOutput(BaseModel):
    """Complete extraction output matching extraction_output_format.json

    This is the root schema that the LLM must return. Extra fields are
    accepted (default Pydantic v2 behavior) but logged so we can detect
    schema drift over time (BUG-032).
    """
    # Explicit config — accept extras quietly, but the LLM should only emit
    # known fields. The pipeline catches drift via post-validation logging.
    model_config = ConfigDict(extra='ignore')

    company: Company
    deal_status: DealStatus
    contacts: List[Contact] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    team_debate: TeamDebate = Field(default_factory=TeamDebate)
    decision_record: DecisionRecord
    company_now: CompanyNow = Field(default_factory=CompanyNow)
    extraction_meta: ExtractionMeta

    @field_validator("contacts", mode="before")
    @classmethod
    def _coerce_contacts(cls, v: Any) -> Any:
        """Tolerate bare-string contacts and contacts missing a name.

        LLM occasionally emits `["Tomás Reyes", "Priya Nair"]` instead of
        proper contact objects. Wrap them; default role to "Other".
        Drop entries with no usable name (Pydantic would otherwise crash
        on a required field).
        """
        if not isinstance(v, list):
            return v
        out: List[Any] = []
        for item in v:
            if item is None:
                continue
            if isinstance(item, str):
                name = item.strip()
                if name:
                    out.append({"name": name, "role": "Other"})
            elif isinstance(item, dict):
                name = (item.get("name") or "").strip() if isinstance(item.get("name"), str) else ""
                if not name:
                    # Try common alternatives the LLM might use.
                    for alt in ("full_name", "display_name", "person"):
                        cand = item.get(alt)
                        if isinstance(cand, str) and cand.strip():
                            name = cand.strip()
                            break
                if name:
                    merged = {**item, "name": name}
                    merged.setdefault("role", "Other")
                    out.append(merged)
        return out

    @field_validator("decision_record", mode="before")
    @classmethod
    def _coerce_decision_record(cls, v: Any) -> Any:
        # If the LLM emits null for the whole block, default-construct it.
        return v if v is not None else {"verdict": "tracking"}

    @field_validator("deal_status", mode="before")
    @classmethod
    def _coerce_deal_status(cls, v: Any) -> Any:
        return v if v is not None else {}

    @model_validator(mode="after")
    def _normalize_cross_block(self) -> "ExtractionOutput":
        """Cross-block normalization that the LLM frequently gets wrong.

        - `deal_status.last_touch_at` must equal the max `occurred_at` across
          all interactions. The LLM sometimes picks the latest narratively
          important interaction instead of the chronologically latest one.
          If the field was missing entirely, backfill it.
        - `deal_momentum` must align with `decision_record.verdict`: a closed
          deal cannot still be "accelerating".
        """
        if self.interactions:
            latest = max(i.occurred_at for i in self.interactions)
            if self.deal_status.last_touch_at != latest:
                if self.deal_status.last_touch_at:
                    self.extraction_meta.warnings.append(
                        f"deal_status.last_touch_at corrected from "
                        f"{self.deal_status.last_touch_at} to {latest} "
                        f"(max of interaction.occurred_at)"
                    )
                self.deal_status.last_touch_at = latest
        elif not self.deal_status.last_touch_at:
            # No interactions and no value — fall back to extraction time so
            # downstream storage doesn't choke on a null required field.
            self.deal_status.last_touch_at = self.extraction_meta.extracted_at
            self.extraction_meta.warnings.append(
                "deal_status.last_touch_at backfilled from extraction_meta.extracted_at "
                "(no interactions present)"
            )

        verdict = self.decision_record.verdict
        momentum = self.company.deal_momentum
        if verdict == "invested" and momentum in {"accelerating", "stalling"}:
            self.extraction_meta.warnings.append(
                f"deal_momentum corrected from '{momentum}' to 'stable' "
                f"(deal already invested)"
            )
            self.company.deal_momentum = "stable"
        elif verdict == "passed" and momentum != "dead":
            self.extraction_meta.warnings.append(
                f"deal_momentum corrected from '{momentum}' to 'dead' "
                f"(deal already passed)"
            )
            self.company.deal_momentum = "dead"

        return self


# Made with Bob