from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Guests ---
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
    communication_preference: str
    ltv_score: float
    satisfaction_score: float
    complaint_history: int
    upsell_acceptance: float
    previous_reviews: int
    notes: Optional[str] = None
    created_at: datetime


# --- Reservations ---
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
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    country: Optional[str] = "Germany"
    language: str = "de"
    travel_type: Optional[str] = "leisure"
    purpose: Optional[str] = None
    children: int = 0
    source: str = "direct"
    room_type: str = "Deluxe Double"
    check_in: date
    check_out: date
    adults: int = 2
    total_amount: float = 280.0
    currency: str = "EUR"
    special_requests: Optional[str] = None
    communication_preference: str = "whatsapp"


# --- Messages ---
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


# --- Reviews ---
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
    themes: Optional[str] = None
    ai_draft_response: Optional[str] = None
    published_response: Optional[str] = None
    responded: bool
    created_at: datetime
    guest_name: Optional[str] = None


class ReviewCreate(BaseModel):
    guest_id: str
    reservation_id: Optional[str] = None
    platform: str = "google"
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = None
    body: str


# --- Offers ---
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
    guest_name: Optional[str] = None


# --- Approvals ---
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
    action: str  # approve | reject
    reviewed_by: str = "Manager"


# --- Tasks ---
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


# --- Events / AI ---
class EventOut(ORMModel):
    id: str
    event_type: str
    payload: str
    source: str
    processed: bool
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
    executed: bool
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
