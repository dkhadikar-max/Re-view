from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(ORMModel):
    id: str
    tenant_id: str
    email: EmailStr
    name: str
    role: str
    is_platform_admin: bool = False


class GuestOut(ORMModel):
    id: str
    property_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    language: str
    stay_count: int
    lifetime_spend: float
    average_booking: float
    travel_type: Optional[str] = None
    purpose: Optional[str] = None
    preferred_room: Optional[str] = None
    children: int
    pets: bool
    dietary_preferences: Optional[str] = None
    birthday: Optional[date] = None
    anniversary: Optional[date] = None
    birthday_locked: bool = False
    anniversary_locked: bool = False
    review_reward_unlocked: bool = False
    communication_preference: str
    ltv_score: float
    satisfaction_score: float
    complaint_history: int
    upsell_acceptance: float
    previous_reviews: int
    notes: Optional[str] = None
    created_at: datetime


class ReservationOut(ORMModel):
    id: str
    property_id: str
    guest_id: str
    external_id: Optional[str] = None
    source: str
    status: str
    room_type: str
    check_in: date
    check_out: date
    adults: int
    children: int
    total_amount: float
    currency: str
    special_requests: Optional[str] = None
    created_at: datetime
    guest_name: Optional[str] = None
    import_session_id: Optional[str] = None


class ReservationCreate(BaseModel):
    guest_name: str = Field(min_length=2, max_length=255)
    guest_email: Optional[EmailStr] = None
    guest_phone: Optional[str] = None
    country: Optional[str] = "Germany"
    language: str = Field(default="de", min_length=2, max_length=8)
    travel_type: Literal["leisure", "business", "family", "luxury"] = "leisure"
    purpose: Optional[str] = None
    children: int = Field(default=0, ge=0, le=10)
    source: str = Field(default="direct", max_length=64)
    room_type: str = Field(default="Deluxe Double", max_length=128)
    check_in: date
    check_out: date
    adults: int = Field(default=2, ge=1, le=10)
    total_amount: float = Field(default=280.0, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    special_requests: Optional[str] = None
    communication_preference: Literal["whatsapp", "email", "sms"] = "whatsapp"

    @model_validator(mode="after")
    def validate_dates(self) -> "ReservationCreate":
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class MessageOut(ORMModel):
    id: str
    guest_id: str
    reservation_id: Optional[str] = None
    channel: str
    direction: str
    language: str
    subject: Optional[str] = None
    body: str
    status: str
    message_type: str
    confidence: Optional[float] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    guest_name: Optional[str] = None


class ReviewOut(ORMModel):
    id: str
    property_id: str
    guest_id: str
    reservation_id: Optional[str] = None
    platform: str
    rating: int
    title: Optional[str] = None
    body: str
    sentiment: str
    themes: list[str] = []
    ai_draft_response: Optional[str] = None
    published_response: Optional[str] = None
    responded: bool
    created_at: datetime
    guest_name: Optional[str] = None


class ReviewCreate(BaseModel):
    guest_id: str
    reservation_id: Optional[str] = None
    platform: str = Field(default="google", max_length=64)
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=255)
    body: str = Field(min_length=5, max_length=5000)


class OfferOut(ORMModel):
    id: str
    reservation_id: str
    name: str
    category: str
    description: Optional[str] = None
    price: float
    currency: str
    status: str
    confidence: float
    created_at: datetime
    accepted_at: Optional[datetime] = None
    payment_link_url: Optional[str] = None
    payment_session_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    guest_name: Optional[str] = None


class ApprovalOut(ORMModel):
    id: str
    approval_type: str
    title: str
    content: str
    status: str
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    confidence: Optional[float] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class ApprovalAction(BaseModel):
    action: Literal["approve", "reject"]


class TaskOut(ORMModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    assignee: Optional[str] = None
    created_at: datetime
    due_at: Optional[datetime] = None


class EventOut(ORMModel):
    id: str
    event_type: str
    payload: str
    source: str
    processed: bool
    status: Optional[str] = None
    created_at: datetime


class AIDecisionOut(ORMModel):
    id: str
    reservation_id: Optional[str] = None
    guest_id: Optional[str] = None
    action: str
    channel: Optional[str] = None
    language: Optional[str] = None
    timing: Optional[str] = None
    offer: Optional[str] = None
    confidence: float
    reasoning: Optional[str] = None
    validated: bool
    validation_error: Optional[str] = None
    executed: bool
    model_name: Optional[str] = None
    created_at: datetime


class PropertyOut(ORMModel):
    id: str
    name: str
    type: str
    city: str
    country: str
    currency: str = "EUR"
    timezone: str
    brand_voice: str
    google_rating: float
    rooms: int
    address: Optional[str] = None
    google_review_url: Optional[str] = None


class PropertyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    country: str = Field(min_length=1, max_length=128)
    currency: str = Field(min_length=3, max_length=8)
    timezone: str = Field(min_length=1, max_length=64)
    rooms: int = Field(ge=1, le=20000)
    brand_voice: str = Field(min_length=1)
    address: Optional[str] = Field(default=None, max_length=500)
    google_review_url: Optional[str] = Field(default=None, max_length=512)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("address", "google_review_url", mode="before")
    @classmethod
    def blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("google_review_url")
    @classmethod
    def validate_review_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Google Review URL must start with http:// or https://")
        return v


class ConnectorOut(ORMModel):
    id: str
    provider: str
    status: str
    last_sync_at: Optional[datetime] = None
    sync_cursor: Optional[str] = None
    created_at: datetime


class WorkflowOut(ORMModel):
    id: str
    name: str
    trigger_event: str
    status: str
    runs: int
    created_at: datetime


class NotificationOut(ORMModel):
    id: str
    title: str
    body: str
    level: str
    read: bool
    created_at: datetime


class DashboardStats(BaseModel):
    arrivals_today: int
    departures_today: int
    pending_messages: int
    negative_reviews: int
    pending_approvals: int
    upsells_waiting: int
    open_tasks: int
    revenue_today: float
    upsell_revenue: float
    repeat_guests: int
    average_spend: float
    review_conversion: float
    google_rating: float
    response_time_hours: float
    ai_saved_hours: float
    occupancy_pct: float
    active_reservations: int
    total_guests: int
    currency: str = "EUR"
    metrics_note: str = (
        "revenue_today = in-house reservation room revenue for stays covering today; "
        "response_time_hours and ai_saved_hours are operational estimates derived from "
        "sent messages and executed AI decisions."
    )


class IntelligenceTheme(BaseModel):
    theme: str
    mentions: int
    sentiment: str


class IntelligenceReport(BaseModel):
    themes: list[IntelligenceTheme]
    most_praised: Optional[str] = None
    main_complaint: Optional[str] = None
    total_reviews: int


class SyncResult(BaseModel):
    imported: int
    events_emitted: int
    message: str
    import_session_id: Optional[str] = None
    rows_skipped: int = 0


class CsvRowIssue(BaseModel):
    line_number: int
    field: Optional[str] = None
    message: str


class CsvValidationReport(BaseModel):
    total_rows: int
    valid_count: int
    warning_count: int
    error_count: int
    warnings: list[CsvRowIssue]
    errors: list[CsvRowIssue]


class ImportSummaryOut(BaseModel):
    import_session_id: str
    source: str
    status: str
    reservations_imported: int
    guests_created: int
    returning_guests: int
    birthdays_this_month: int
    reviews_scheduled: int
    upsell_opportunities: int


class ImportSessionListItem(ORMModel):
    id: str
    source: str
    status: str
    filename: Optional[str] = None
    initiated_by: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    rows_total: int
    rows_imported: int
    rows_skipped: int
    rows_failed: int


class ImportSessionDetail(ImportSessionListItem):
    duration_ms: Optional[int] = None
    error_summary: Optional[str] = None
    warnings: list[CsvRowIssue] = []
    errors: list[CsvRowIssue] = []


class PdfExtractionIssue(BaseModel):
    field: Optional[str] = None
    message: str


class PdfExtractedRow(BaseModel):
    """One reservation extracted from a PDF, staged for mandatory human
    review (PDF_IMPORT.md §7) — nothing here has been imported yet.
    `reservation` is None when extraction couldn't produce a valid
    `ReservationCreate` at all (e.g. missing dates); the row still shows
    up as Needs Review so a human can fix it via Manual Entry instead of
    the PDF simply vanishing.
    """

    row_index: int
    review_state: Literal["ready_to_import", "needs_review"]
    confirmation_number: Optional[str] = None
    reservation: Optional[ReservationCreate] = None
    issues: list[PdfExtractionIssue] = []
    raw_text_excerpt: Optional[str] = None


class PdfValidationReport(BaseModel):
    filename: str
    total_reservations: int
    ready_count: int
    needs_review_count: int
    rows: list[PdfExtractedRow]


class PdfConfirmRow(BaseModel):
    """What the Review screen submits back per approved (optionally
    edited) row. `confirmation_number` is required here even though it
    was optional during extraction — a human confirming a Needs Review
    row without one is exactly the "guessing an identity" case §11.1
    decided against; the API rejects it rather than silently assigning
    a random one."""

    confirmation_number: str = Field(min_length=1, max_length=128)
    reservation: ReservationCreate


class PdfImportRequest(BaseModel):
    filename: Optional[str] = None
    rows: list[PdfConfirmRow] = Field(min_length=1)


class PdfImportResult(BaseModel):
    import_session_id: str
    imported: int
    duplicates_skipped: int
    message: str


class DecideResult(BaseModel):
    decision: AIDecisionOut
    execution: dict[str, Any]


class WorkerResult(BaseModel):
    events_processed: int
    messages_delivered: int
    workflows_advanced: int
    celebrate_campaigns: dict[str, int] = {}


class AuditOut(ORMModel):
    id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    details: Optional[str] = None
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    service: str
    version: str
    database: str
    environment: str
    platform: str = "Argus OS"
    storage_backend: str | None = None
    storage_durable: bool | None = None
    storage_warning: str | None = None



TokenResponse.model_rebuild()
