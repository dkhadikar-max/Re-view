from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def uid() -> str:
    return str(uuid.uuid4())


class ReservationStatus(str, enum.Enum):
    confirmed = "confirmed"
    checked_in = "checked_in"
    checked_out = "checked_out"
    cancelled = "cancelled"


class MessageChannel(str, enum.Enum):
    whatsapp = "whatsapp"
    email = "email"
    sms = "sms"


class MessageStatus(str, enum.Enum):
    draft = "draft"
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    pending_approval = "pending_approval"


class ReviewSentiment(str, enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class TaskStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class OfferStatus(str, enum.Enum):
    available = "available"
    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class EventStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"


class WorkflowRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(64), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_tenant_email"),
        CheckConstraint("role IN ('viewer','staff','manager','admin')", name="ck_user_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64), default="manager")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(64), default="hotel")
    city: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    brand_voice: Mapped[str] = mapped_column(Text, default="Warm, professional, and helpful.")
    google_rating: Mapped[float] = mapped_column(Float, default=4.5)
    rooms: Mapped[int] = mapped_column(Integer, default=40)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guests: Mapped[list[Guest]] = relationship(back_populates="property")
    reservations: Mapped[list[Reservation]] = relationship(back_populates="property")


class Guest(Base):
    __tablename__ = "guests"
    __table_args__ = (
        CheckConstraint("ltv_score >= 0 AND ltv_score <= 100", name="ck_guest_ltv"),
        CheckConstraint(
            "satisfaction_score >= 0 AND satisfaction_score <= 100", name="ck_guest_sat"
        ),
        CheckConstraint("lifetime_spend >= 0", name="ck_guest_spend"),
        CheckConstraint("children >= 0", name="ck_guest_children"),
        Index("ix_guests_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(32), default="en")
    stay_count: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_spend: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    average_booking: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    travel_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    preferred_room: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    children: Mapped[int] = mapped_column(Integer, default=0)
    pets: Mapped[bool] = mapped_column(Boolean, default=False)
    dietary_preferences: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    anniversary: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    birthday_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    anniversary_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    birthday_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    anniversary_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reward_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reward_unlocked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    celebrate_dates_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    communication_preference: Mapped[str] = mapped_column(String(32), default="whatsapp")
    previous_reviews: Mapped[int] = mapped_column(Integer, default=0)
    complaint_history: Mapped[int] = mapped_column(Integer, default=0)
    upsell_acceptance: Mapped[float] = mapped_column(Float, default=0.0)
    ltv_score: Mapped[float] = mapped_column(Float, default=50.0)
    satisfaction_score: Mapped[float] = mapped_column(Float, default=70.0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    property: Mapped[Property] = relationship(back_populates="guests")
    reservations: Mapped[list[Reservation]] = relationship(back_populates="guest")
    messages: Mapped[list[Message]] = relationship(back_populates="guest")
    reviews: Mapped[list[Review]] = relationship(back_populates="guest")


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_res_amount"),
        CheckConstraint("adults >= 1", name="ck_res_adults"),
        CheckConstraint("children >= 0", name="ck_res_children"),
        CheckConstraint("check_out > check_in", name="ck_res_dates"),
        UniqueConstraint("tenant_id", "source", "external_id", name="uq_res_external"),
        Index("ix_res_tenant_checkin", "tenant_id", "check_in"),
        Index("ix_res_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="direct")
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus), default=ReservationStatus.confirmed
    )
    room_type: Mapped[str] = mapped_column(String(128), default="Standard")
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    adults: Mapped[int] = mapped_column(Integer, default=2)
    children: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    special_requests: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    property: Mapped[Property] = relationship(back_populates="reservations")
    guest: Mapped[Guest] = relationship(back_populates="reservations")
    messages: Mapped[list[Message]] = relationship(back_populates="reservation")
    offers: Mapped[list[Offer]] = relationship(back_populates="reservation")
    reviews: Mapped[list[Review]] = relationship(back_populates="reservation")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_msg_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), index=True)
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True, index=True
    )
    channel: Mapped[MessageChannel] = mapped_column(Enum(MessageChannel))
    direction: Mapped[str] = mapped_column(String(16), default="outbound")
    language: Mapped[str] = mapped_column(String(32), default="en")
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.draft
    )
    message_type: Mapped[str] = mapped_column(String(64), default="general")
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guest: Mapped[Guest] = relationship(back_populates="messages")
    reservation: Mapped[Optional[Reservation]] = relationship(back_populates="messages")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating"),
        Index("ix_review_tenant_rating", "tenant_id", "rating"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), index=True)
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(64), default="google")
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[ReviewSentiment] = mapped_column(
        Enum(ReviewSentiment), default=ReviewSentiment.neutral
    )
    themes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_draft_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guest: Mapped[Guest] = relationship(back_populates="reviews")
    reservation: Mapped[Optional[Reservation]] = relationship(back_populates="reviews")


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_offer_price"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64), default="upsell")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus), default=OfferStatus.offered)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    payment_link_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    payment_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    reservation: Mapped[Reservation] = relationship(back_populates="offers")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(64), default="cross_sell")
    status: Mapped[str] = mapped_column(String(32), default="active")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_task_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.open)
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.medium
    )
    related_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    related_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assignee: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    trigger_event: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active")
    definition: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    trigger_event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        Enum(WorkflowRunStatus), default=WorkflowRunStatus.pending
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    context: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_event_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(64), default="system")
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.pending)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AIDecision(Base):
    __tablename__ = "ai_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True
    )
    guest_id: Mapped[Optional[str]] = mapped_column(ForeignKey("guests.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    channel: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    timing: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    offer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str] = mapped_column(Text, default="{}")
    model_name: Mapped[str] = mapped_column(String(64), default="heuristic-v1")
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_tenant_provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="connected")
    config_encrypted: Mapped[str] = mapped_column(Text, default="")
    sync_cursor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approval_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    approval_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending
    )
    related_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    related_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(32), default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    related_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    related_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CouponStatus(str, enum.Enum):
    active = "active"
    redeemed = "redeemed"
    expired = "expired"
    cancelled = "cancelled"


class CelebrateOfferType(str, enum.Enum):
    birthday = "birthday"
    anniversary = "anniversary"


class CelebrateRewardConfig(Base):
    """Per-tenant Celebrate Rewards merchant configuration."""

    __tablename__ = "celebrate_reward_configs"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_celebrate_config_tenant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    birthday_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    birthday_discount_pct: Mapped[float] = mapped_column(Float, default=20.0)
    birthday_days_before: Mapped[int] = mapped_column(Integer, default=7)
    birthday_days_after: Mapped[int] = mapped_column(Integer, default=7)
    birthday_min_spend: Mapped[float] = mapped_column(Numeric(12, 2), default=1000)
    birthday_max_uses_per_year: Mapped[int] = mapped_column(Integer, default=1)
    birthday_stackable: Mapped[bool] = mapped_column(Boolean, default=False)
    anniversary_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anniversary_discount_pct: Mapped[float] = mapped_column(Float, default=15.0)
    anniversary_days_before: Mapped[int] = mapped_column(Integer, default=3)
    anniversary_days_after: Mapped[int] = mapped_column(Integer, default=3)
    anniversary_min_spend: Mapped[float] = mapped_column(Numeric(12, 2), default=2000)
    anniversary_max_uses_per_year: Mapped[int] = mapped_column(Integer, default=1)
    anniversary_stackable: Mapped[bool] = mapped_column(Boolean, default=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_coupon_code"),
        Index("ix_coupon_guest_type_year", "tenant_id", "guest_id", "offer_type", "year"),
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="ck_coupon_pct"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), index=True)
    offer_type: Mapped[CelebrateOfferType] = mapped_column(Enum(CelebrateOfferType))
    code: Mapped[str] = mapped_column(String(32))
    discount_pct: Mapped[float] = mapped_column(Float)
    min_spend: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    year: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[CouponStatus] = mapped_column(
        Enum(CouponStatus), default=CouponStatus.active
    )
    stackable: Mapped[bool] = mapped_column(Boolean, default=False)
    personalized_perk: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    redemption_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CelebrateDateAudit(Base):
    """Immutable audit trail for birthday/anniversary unlocks and changes."""

    __tablename__ = "celebrate_date_audits"
    __table_args__ = (Index("ix_celebrate_audit_guest", "tenant_id", "guest_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(255))
    changed_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(String(64))  # lock | unlock | set | confirm
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
