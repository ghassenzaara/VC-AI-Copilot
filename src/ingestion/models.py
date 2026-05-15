"""Pydantic models for data source validation

All models match the exact structure defined in data-forms.md
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ============================================
# GRANOLA MODELS
# ============================================

class GranolaOwner(BaseModel):
    """Granola note owner"""
    name: str
    email: str


class GranolaCalendarEvent(BaseModel):
    """Granola calendar event details"""
    scheduled_start_time: str
    scheduled_end_time: str
    organiser: str


class GranolaAttendee(BaseModel):
    """Granola meeting attendee"""
    name: str
    email: str


class GranolaSpeaker(BaseModel):
    """Granola transcript speaker"""
    source: str  # "microphone" or "speaker"


class GranolaTranscriptSegment(BaseModel):
    """Granola transcript segment"""
    speaker: GranolaSpeaker
    text: str
    start_time: str
    end_time: str


class GranolaNote(BaseModel):
    """Granola meeting note (data-forms.md lines 7-40)"""
    id: str
    title: str
    owner: GranolaOwner
    created_at: str
    calendar_event: GranolaCalendarEvent
    attendees: List[GranolaAttendee]
    summary_text: str
    transcript: List[GranolaTranscriptSegment]


# ============================================
# AFFINITY MODELS
# ============================================

class AffinityInteractionDates(BaseModel):
    """Affinity interaction dates"""
    last_event_date: Optional[str] = None
    next_event_date: Optional[str] = None


class AffinityOrganization(BaseModel):
    """Affinity organization (data-forms.md lines 50-62)"""
    id: int
    name: str
    domain: Optional[str] = None
    domains: List[str] = Field(default_factory=list)
    person_ids: List[int] = Field(default_factory=list)
    opportunity_ids: List[int] = Field(default_factory=list)
    interaction_dates: Optional[AffinityInteractionDates] = None


class AffinityPerson(BaseModel):
    """Affinity person (data-forms.md lines 65-74)"""
    id: int
    first_name: str
    last_name: str
    primary_email: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    organization_ids: List[int] = Field(default_factory=list)


class AffinityListEntry(BaseModel):
    """Affinity opportunity list entry"""
    list_id: int
    created_at: str


class AffinityOpportunity(BaseModel):
    """Affinity opportunity (data-forms.md lines 77-90)"""
    id: int
    name: str
    organization_ids: List[int] = Field(default_factory=list)
    person_ids: List[int] = Field(default_factory=list)
    list_entries: List[AffinityListEntry] = Field(default_factory=list)


class AffinityFieldValue(BaseModel):
    """Affinity field value (data-forms.md lines 94-103)"""
    field_id: int
    entity_id: int
    value: Any  # Can be string, int, float, date


class AffinityNote(BaseModel):
    """Affinity note (data-forms.md lines 107-115)"""
    id: int
    content: str
    created_at: str
    person_ids: List[int] = Field(default_factory=list)


class AffinityData(BaseModel):
    """Complete Affinity data bundle"""
    organization: AffinityOrganization
    persons: List[AffinityPerson] = Field(default_factory=list)
    opportunities: List[AffinityOpportunity] = Field(default_factory=list)
    field_values: List[AffinityFieldValue] = Field(default_factory=list)
    notes: List[AffinityNote] = Field(default_factory=list)
    interactions: Optional[AffinityInteractionDates] = None


# ============================================
# GMAIL MODELS
# ============================================

class GmailHeader(BaseModel):
    """Gmail message header"""
    name: str
    value: str


class GmailBody(BaseModel):
    """Gmail message body"""
    data: str


class GmailPart(BaseModel):
    """Gmail message part"""
    mimeType: str
    body: GmailBody


class GmailPayload(BaseModel):
    """Gmail message payload"""
    headers: List[GmailHeader]
    parts: List[GmailPart] = Field(default_factory=list)


class GmailMessage(BaseModel):
    """Gmail message (data-forms.md lines 132-154)"""
    id: str
    threadId: str
    internalDate: str
    payload: GmailPayload
    snippet: str
    
    def get_header(self, name: str) -> Optional[str]:
        """Get header value by name"""
        for header in self.payload.headers:
            if header.name.lower() == name.lower():
                return header.value
        return None
    
    def get_body_text(self) -> str:
        """Extract plain text body"""
        for part in self.payload.parts:
            if part.mimeType == "text/plain":
                return part.body.data
        return ""


# ============================================
# SLACK MODELS
# ============================================

class SlackReaction(BaseModel):
    """Slack message reaction"""
    name: str
    count: int


class SlackMessage(BaseModel):
    """Slack message (data-forms.md lines 164-174)"""
    ts: str
    user: str  # Pre-resolved to real_name in mock data
    text: str
    thread_ts: Optional[str] = None
    reply_count: Optional[int] = 0
    reactions: List[SlackReaction] = Field(default_factory=list)


class SlackChannel(BaseModel):
    """Slack channel (data-forms.md lines 180-185)"""
    id: str
    name: str
    is_private: bool = False


class SlackUserProfile(BaseModel):
    """Slack user profile"""
    email: str
    title: Optional[str] = None


class SlackUser(BaseModel):
    """Slack user (data-forms.md lines 189-197)"""
    id: str
    real_name: str
    profile: SlackUserProfile


class SlackData(BaseModel):
    """Complete Slack data bundle"""
    message: SlackMessage
    channel: SlackChannel
    users: List[SlackUser] = Field(default_factory=list)


# ============================================
# UNIFIED INTERACTION MODEL
# ============================================

class UnifiedInteraction(BaseModel):
    """Standardized interaction format for all sources
    
    Note: This is the pre-LLM interaction type. The LLM will later re-classify
    interactions into extraction_output_format.json types (intro_meeting, deep_dive, etc.)
    """
    id: str
    source: Literal["granola", "affinity", "gmail", "slack"]
    type: Literal["meeting", "email", "message", "note"]  # Pre-LLM classification
    title: str
    content: str
    occurred_at: str  # Must be UTC ISO 8601 format
    participants: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_data: Dict[str, Any] = Field(default_factory=dict)


# ============================================
# COMPANY AGGREGATION MODEL
# ============================================

class CompanyData(BaseModel):
    """Aggregated company data from all sources"""
    company_name: str
    company_id: Optional[str] = None
    interactions: List[UnifiedInteraction] = Field(default_factory=list)
    contacts: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Source tracking
    granola_notes: List[GranolaNote] = Field(default_factory=list)
    affinity_data: Optional[AffinityData] = None
    gmail_messages: List[GmailMessage] = Field(default_factory=list)
    slack_messages: List[SlackData] = Field(default_factory=list)

# Made with Bob
