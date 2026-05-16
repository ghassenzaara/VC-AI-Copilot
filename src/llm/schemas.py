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


# ============================================
# COMPANY BLOCK
# ============================================

class CompanySource(BaseModel):
    """Company data source tracking"""
    types: List[Literal["granola", "affinity", "slack", "gmail"]]
    external_id: Optional[str] = None


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
        return v if v in {"Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Growth"} else None

    @field_validator("deal_momentum", mode="before")
    @classmethod
    def _coerce_momentum(cls, v: Any) -> Any:
        return v if v in {"accelerating", "stable", "stalling", "dead"} else None


# ============================================
# DEAL STATUS BLOCK
# ============================================

class DealStatus(BaseModel):
    """Current deal pipeline status"""
    pipeline_stage: Literal["Tracking", "First call", "Diligence", "IC review", "Decision"]
    last_touch_at: str  # ISO 8601 datetime
    next_step: Optional[str] = None
    owner: Optional[str] = None

    @field_validator("pipeline_stage", mode="before")
    @classmethod
    def _coerce_stage(cls, v: Any) -> Any:
        return v if v in {"Tracking", "First call", "Diligence", "IC review", "Decision"} else "Tracking"

    @field_validator("last_touch_at")
    @classmethod
    def _v_last_touch(cls, v: str) -> str:
        # last_touch_at is required, so validate strictly.
        validated = _validate_datetime(v)
        if validated is None:
            raise ValueError("last_touch_at is required")
        return validated


# ============================================
# CONTACTS BLOCK
# ============================================

_VALID_ROLES = {"Founder", "CEO", "CTO", "COO", "Investor", "Operator", "Other"}


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
        return v if v in _VALID_ROLES else "Other"


# ============================================
# INTERACTIONS BLOCK
# ============================================

class InteractionSource(BaseModel):
    """Interaction source tracking"""
    type: Literal["granola", "affinity", "slack", "gmail"]
    url: Optional[str] = None
    external_id: Optional[str] = None


_VALID_METRIC_LABELS = {"ARR", "MRR", "customers", "burn", "runway", "growth_rate", "margin", "headcount", "other"}


class MetricMention(BaseModel):
    """Metric mentioned in interaction"""
    label: Literal["ARR", "MRR", "customers", "burn", "runway", "growth_rate", "margin", "headcount", "other"]
    value: str
    as_of: Optional[str] = None  # YYYY-MM-DD

    @field_validator("label", mode="before")
    @classmethod
    def _coerce_label(cls, v: Any) -> Any:
        return v if v in _VALID_METRIC_LABELS else "other"

    @field_validator("as_of")
    @classmethod
    def _v_as_of(cls, v: Optional[str]) -> Optional[str]:
        return _validate_date(v)


class Quote(BaseModel):
    """Direct quote from interaction"""
    speaker: str
    text: str


_METRIC_LABEL_MAP = {
    "mrr": "MRR", "arr": "ARR", "customer": "customers", "burn": "burn",
    "runway": "runway", "growth": "growth_rate", "mom": "growth_rate",
    "yoy": "growth_rate", "margin": "margin", "headcount": "headcount",
    "employee": "headcount", "team size": "headcount",
}


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
                lower = item.lower()
                label = next(
                    (lbl for key, lbl in _METRIC_LABEL_MAP.items() if key in lower),
                    "other",
                )
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


_VALID_INTERACTION_TYPES = {
    "intro_meeting", "deep_dive", "demo", "reference_call",
    "email", "slack_message", "memo", "ic_review", "other",
}


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
        return v if v in _VALID_INTERACTION_TYPES else "other"

    @field_validator("channel", mode="before")
    @classmethod
    def _coerce_channel(cls, v: Any) -> Any:
        return v if v in {"video", "in_person", "phone", "email", "slack", "other"} else "other"

    @field_validator("sentiment", mode="before")
    @classmethod
    def _coerce_sentiment(cls, v: Any) -> Any:
        return v if v in {"positive", "neutral", "negative"} else "neutral"

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


# ============================================
# TEAM DEBATE BLOCK
# ============================================

class Argument(BaseModel):
    """Argument for or against investing"""
    argument: str
    supporter: Optional[str] = None
    evidence: Optional[str] = None


class TeamDebate(BaseModel):
    """Internal team debate about the deal"""
    detected: bool = False
    for_arguments: List[Argument] = Field(default_factory=list)
    against_arguments: List[Argument] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)


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
        return v if v in {"tracking", "diligence", "invested", "passed"} else "tracking"

    @field_validator("decided_at")
    @classmethod
    def _v_decided_at(cls, v: Optional[str]) -> Optional[str]:
        return _validate_datetime(v)


# ============================================
# COMPANY NOW BLOCK (populated by query engine)
# ============================================

class Funding(BaseModel):
    """Company funding information"""
    last_round_stage: Optional[str] = None
    last_round_amount_usd: Optional[float] = None
    total_raised_usd: Optional[float] = None


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

    @model_validator(mode="after")
    def _normalize_cross_block(self) -> "ExtractionOutput":
        """Cross-block normalization that the LLM frequently gets wrong.

        - `deal_status.last_touch_at` must equal the max `occurred_at` across
          all interactions. The LLM sometimes picks the latest narratively
          important interaction instead of the chronologically latest one.
        - `deal_momentum` must align with `decision_record.verdict`: a closed
          deal cannot still be "accelerating".
        """
        if self.interactions:
            latest = max(i.occurred_at for i in self.interactions)
            if self.deal_status.last_touch_at != latest:
                self.extraction_meta.warnings.append(
                    f"deal_status.last_touch_at corrected from "
                    f"{self.deal_status.last_touch_at} to {latest} "
                    f"(max of interaction.occurred_at)"
                )
                self.deal_status.last_touch_at = latest

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