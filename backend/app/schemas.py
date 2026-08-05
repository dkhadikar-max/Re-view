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
    timezone: str
    brand_voice: str
    google_rating: float
    rooms: int


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


TokenResponse.model_rebuild()
