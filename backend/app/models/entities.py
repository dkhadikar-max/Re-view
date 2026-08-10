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


class ActionEventStatus(str, enum.Enum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"
    completed = "completed"
    failed = "failed"
    escalated = "escalated"


class ActorType(str, enum.Enum):
    """Who performed an `ActionEvent` — a platform contract as of PR #20
    review, frozen alongside `action_type` (CONCIERGE.md's Action Ledger
    section). Stored uppercase (unlike this file's other enums) to match
    that exact contract. `ai`/`system` are the only values the Router
    emits today; `guest`/`staff` are reserved for the Conversation
    Manager (a guest confirming/declining, staff completing a task)."""

    ai = "AI"
    guest = "GUEST"
    staff = "STAFF"
    system = "SYSTEM"


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
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    brand_voice: Mapped[str] = mapped_column(Text, default="Warm, professional, and helpful.")
    google_rating: Mapped[float] = mapped_column(Float, default=4.5)
    rooms: Mapped[int] = mapped_column(Integer, default=40)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    google_review_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Meta's inbound webhook payload includes this on every message
    # (value.metadata.phone_number_id) — set once per property when its
    # WhatsApp number is provisioned under ReVisit's WABA (CONCIERGE.md
    # §3), used to route an inbound message to the right tenant instead
    # of guessing from the guest's own phone number.
    whatsapp_phone_number_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guests: Mapped[list[Guest]] = relationship(back_populates="property")
    reservations: Mapped[list[Reservation]] = relationship(back_populates="property")
    knowledge_base: Mapped[Optional["PropertyKnowledgeBase"]] = relationship(
        back_populates="property", uselist=False
    )


class PropertyKnowledgeBase(Base):
    """Structured per-property facts the AI Concierge's FAQ Agent answers
    from (CONCIERGE.md §7) — no RAG/vectors, one row per property.
    Every field is optional: an empty field is an honest "don't know",
    not a reason to guess. `restaurants`/`cafes`/`nearby_attractions` are
    staff-curated free text (their own picks, their own voice) — the
    concierge pushes this content, it never generates it.
    """

    __tablename__ = "property_knowledge_base"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("properties.id"), unique=True, index=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)

    # Practical info
    wifi_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    breakfast_hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pool_hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gym_hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    spa_hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parking_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checkin_time: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    checkout_time: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    late_checkout_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    airport_transfer_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Policies
    pet_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    house_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    policies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Local recommendations — staff-curated, see class docstring
    restaurants: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cafes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nearby_attractions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Services & emergency
    services: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    room_service_hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    emergency_contacts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    property: Mapped[Property] = relationship(back_populates="knowledge_base")


class PropertyService(Base):
    """A hotel-configured, bookable service — the source of truth the
    Revenue Agent recommends from. `service_type` is a plain string, not
    a hard enum: the well-known identifiers (late_checkout, early_checkin,
    breakfast, dinner, room_service, laundry, spa, airport_transfer,
    parking, kids_activities, tours, gym, cab_booking) are what the
    Revenue Agent's own trigger patterns (`revenue_agent.py`) key off
    of, but "any service configured by the hotel" (per spec) means a
    hotel can also add a custom one — it's still reachable via a
    literal name-mention fallback, it just won't be recognized from
    action-oriented free-text phrasing without a matching fixed
    pattern, the same honest limitation PDF_IMPORT.md's heuristic
    parser already documents for its own closed vocabulary.

    `room_service` is shared vocabulary with the Ordering Agent
    (`ordering_agent.py`, MENU_ORDERING.md): Revenue Agent quotes/books
    it as a paid extra when explicitly asked in a booking sense ("can I
    order room service"), Ordering Agent hands off to it as the active
    food-ordering channel when the guest is hungry — the Router
    priority order (Ordering before Revenue) is what resolves which one
    actually answers a given message; this table doesn't need to care.
    `breakfast`/`dinner` here are bookable add-on packages, distinct
    from actively ordering food off a menu (still MENU_ORDERING.md's
    frozen, not-yet-built `MenuItem` domain).
    """

    __tablename__ = "property_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)

    service_type: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    complimentary: Mapped[bool] = mapped_column(Boolean, default=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PropertyPackage(Base):
    """A hotel-configured, occasion-triggered bundle (Romance Package,
    Celebration Package). `occasions` is a comma-separated list of
    trigger keywords (e.g. "anniversary,honeymoon") — a plain string,
    not a join table, matching this app's convention of keeping simple
    list-like fields as text (same pattern PropertyKnowledgeBase's
    restaurants/attractions fields already use) rather than
    over-normalizing a small, hotel-curated list.
    """

    __tablename__ = "property_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occasions: Mapped[str] = mapped_column(String(255), default="")
    price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    available: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class MenuItem(Base):
    """A hotel-uploaded dish/drink — MENU_ORDERING.md §3.1, one row per
    item. A hotel can have several menus (breakfast, room service, bar)
    distinguished by `menu_name`, not separate tables.

    Uploaded via `MenuImporter` (`app/services/menu_importer.py`) and
    always human-reviewed before creation — nothing here was ever
    written by an AI extraction pass alone (MENU_ORDERING.md's own
    guardrail, restated in `menu_importer.py`'s docstring). `id` stays
    stable across every subsequent edit (never delete-and-recreate) —
    this is the identity a future `Order.items` snapshot
    (MENU_ORDERING.md §6, not yet built) will reference, and the
    identity a future menu-version evidence chain for Argus depends on
    staying meaningful over time.

    Provenance is deliberately NOT a new subsystem: `source_import_id`
    answers "which upload produced this row" (the existing
    `ImportSession` primitive, reused, not extended); every edit after
    that goes through the existing `AuditLog`/`write_audit` mechanism
    (same as `PropertyKnowledgeBase`'s own editor). Together those two
    already-existing mechanisms answer "which source produced this item,
    and was it subsequently edited by staff" without a dedicated
    versioning table.
    """

    __tablename__ = "menu_items"
    __table_args__ = (
        Index("ix_menu_item_tenant_id", "tenant_id"),
        Index("ix_menu_item_property_id", "property_id"),
        Index("ix_menu_item_source_import_id", "source_import_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"))

    menu_name: Mapped[str] = mapped_column(String(128), default="Menu")
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    vegetarian: Mapped[bool] = mapped_column(Boolean, default=False)
    vegan: Mapped[bool] = mapped_column(Boolean, default=False)
    gluten_free: Mapped[bool] = mapped_column(Boolean, default=False)
    spicy: Mapped[bool] = mapped_column(Boolean, default=False)

    # Which upload produced this row — nullable because a future
    # "add one item by hand" path (not built yet) would have no import
    # to point to; every row created by MenuImporter always sets it.
    source_import_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("import_sessions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


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
    import_session_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("import_sessions.id"), nullable=True, index=True
    )
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
    __table_args__ = (
        Index("ix_msg_tenant_status", "tenant_id", "status"),
        # PILOT_READINESS.md §1 — supports the (tenant_id,
        # provider_message_id) webhook-dedup lookup in
        # `ingest_inbound_whatsapp`. Not unique: most rows legitimately
        # have a NULL provider_message_id.
        Index("ix_msg_tenant_provider_message_id", "tenant_id", "provider_message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"), index=True)
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True, index=True
    )
    channel: Mapped[MessageChannel] = mapped_column(Enum(MessageChannel))
    direction: Mapped[str] = mapped_column(String(16), default="outbound")
    # Declared/preferred language (Guest.language, copied at creation) —
    # NOT the same concept as `detected_language` below. TRANSLATION_LAYER.md
    # §2 constraint 3 / the CTO's own distinction: this field predates the
    # Translation Layer and must not be reused for it.
    language: Mapped[str] = mapped_column(String(32), default="en")
    # Translation Layer (TRANSLATION_LAYER.md) — the language actually
    # detected for THIS inbound message, independent of the guest's
    # declared `language` above. Null for outbound messages and for any
    # inbound message ingested before detection existed.
    detected_language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    # Translation Layer — the internal English representation of `body`,
    # populated only when `detected_language` is non-English (TRANSLATION_
    # LAYER.md §3's no-op rule: an English message never gets a redundant
    # copy here). `body` itself is NEVER overwritten — constraint 4.
    normalized_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.draft
    )
    message_type: Mapped[str] = mapped_column(String(64), default="general")
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # PILOT_READINESS.md §2 — how many delivery retries this message has
    # already had. Only ever incremented on a `failed` message picked up
    # again by `process_due_messages`; the original attempt doesn't
    # count. Once >= MAX_OUTBOUND_RETRIES (messaging.py), a failed
    # message is left alone — queryable as an exhausted, needs-attention
    # delivery, not silently retried forever.
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guest: Mapped[Guest] = relationship(back_populates="messages")
    reservation: Mapped[Optional[Reservation]] = relationship(back_populates="messages")


class ActionEvent(Base):
    """The Action Ledger — CONCIERGE.md's "Action Ledger" section.
    ReVisit's operational record of every meaningful AI decision, and
    the future learning dataset for Argus (ReVisit's parent product).
    Not used for runtime decision-making by anything in this codebase
    today — this table exists purely to capture what happened, not to
    influence what happens next.

    Immutable by convention, not by database constraint: only
    `ActionLogger` (`app/services/action_logger.py`) may create a row,
    and only its own `log_accept`/`log_reject`/`log_complete`/
    `log_failure` methods may ever change one after creation — and even
    then, only the `status` field. Every other field is set once, at
    `log_action()` time, and never rewritten.

    `intent`/`agent`/`action_type` are plain strings, not hard enums —
    same "closed vocabulary today, extensible tomorrow" reasoning
    `PropertyService.service_type` already documents; `agent` is `None`
    for events that never reached an agent (e.g. an Escalation Filter
    trip or an UNKNOWN intent).

    `input_summary`/`decision`/`output_summary` are short, structured
    descriptions built from each agent's own already-structured
    metadata (a service name, a KB topic, a memory field) — never the
    guest's raw message text, and never a secret value (a KB fact like
    `wifi_password` is referenced by topic only, not quoted). The full
    transcript already lives in `Message`/Conversation History; this
    table isn't a second copy of it, no summarization model or
    analytics involved, just concise templating (`concierge_router.py`'s
    own `_summarize_*` helpers).

    `correlation_id` groups every `ActionEvent` that stems from the same
    guest interaction, even across separate turns — e.g. "Revenue Offer
    Proposed" now and "Guest Accepted"/"Staff Completed" later, once a
    reply resolves it. A fresh one is generated per `route()` call by
    default (`ActionLogger.log_action`); carrying the *same* one across
    a multi-turn resolution is the Conversation Manager's job once it
    exists (not yet — see roadmap), by passing the original event's
    `correlation_id` through when it re-dispatches to the owning agent.

    `actor` identifies who performed the action — `ActorType.ai` when a
    specific agent (FAQ/Revenue/Guest Memory/Ordering) actually ran and
    produced the outcome, whether that outcome was an answer, a
    proposal, or the agent's own `should_escalate`/`handled=False`.
    `ActorType.system` is for a decision made *without* any agent
    running at all — the Escalation Filter's own hard-safety pattern
    match, an `UNKNOWN` intent classification, or an auto-acknowledged
    `SMALL_TALK`. `ActorType.guest`/`ActorType.staff` are reserved for
    the Conversation Manager (a guest confirming/declining, staff
    completing a task) — required on every row, same "identify who did
    this" discipline the review that added it described.
    """

    __tablename__ = "action_events"
    __table_args__ = (
        Index("ix_action_event_tenant_id", "tenant_id"),
        Index("ix_action_event_guest_id", "guest_id"),
        Index("ix_action_event_reservation_id", "reservation_id"),
        Index("ix_action_event_conversation_id", "conversation_id"),
        Index("ix_action_event_created_at", "created_at"),
        Index("ix_action_event_action_type", "action_type"),
        Index("ix_action_event_correlation_id", "correlation_id"),
        Index("ix_action_event_actor", "actor"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    correlation_id: Mapped[str] = mapped_column(String(36), default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"))
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    intent: Mapped[str] = mapped_column(String(32))
    agent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64))
    # values_callable is required here (unlike every other Enum column
    # in this file): SQLAlchemy's Enum type defaults to storing a Python
    # enum's *name*, not its .value. Every other enum in this file has
    # name == value (e.g. ActionEventStatus.proposed == "proposed"), so
    # the default was invisible; ActorType.ai == "AI" deliberately
    # differs (lowercase member for callers, uppercase stored value per
    # the platform contract) and would otherwise silently insert "ai"
    # against a Postgres enum type that only accepts "AI".
    actor: Mapped[ActorType] = mapped_column(
        Enum(ActorType, values_callable=lambda enum_cls: [member.value for member in enum_cls])
    )

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    input_summary: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[ActionEventStatus] = mapped_column(
        Enum(ActionEventStatus), default=ActionEventStatus.proposed
    )
    # Python attribute avoids colliding with SQLAlchemy's own
    # declarative `Base.metadata` class attribute; the physical column
    # is still named "metadata" per spec.
    event_metadata: Mapped[str] = mapped_column("metadata", Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PendingActionStatus(str, enum.Enum):
    pending = "pending"
    resolved = "resolved"
    cancelled = "cancelled"
    expired = "expired"


class PendingAction(Base):
    """The Conversation Manager's active-workflow tracker — CONCIERGE.md
    §5.5/§16. Answers a narrower question than the Action Ledger does:
    not "what happened" (that's `ActionEvent`, immutable, append-only),
    but "is there something this guest still needs to respond to, right
    now?" `ConversationManager` (`app/services/conversation_manager.py`)
    is the only component that creates or transitions a row here.

    Deliberately NOT itself event-sourced — `status` transitions exactly
    once (`pending` -> `resolved`/`cancelled`/`expired`) and is never
    reopened or reused for a second proposal. The event-sourcing happens
    one level up: every transition here is mirrored by a new
    `ActionEvent` sharing this row's `correlation_id` (e.g.
    `OFFER_PROPOSED` then `OFFER_ACCEPTED`), so the full lifecycle stays
    fully replayable from `ActionEvent` alone — this table is a
    fast-lookup index into "what's still open", not a second source of
    truth. `origin_action_type` is a copy of the triggering event's
    `action_type` (e.g. `"OFFER_PROPOSED"`), so `ConversationManager` can
    look up which domain-specific resolution event to emit later
    (`OFFER_ACCEPTED`/`OFFER_REJECTED`/`OFFER_EXPIRED`) without needing
    to re-derive *why* the proposal was made.

    One active (`status=pending`) row per `(tenant_id, guest_id)` at a
    time, enforced by `ConversationManager`, not a database constraint:
    a second proposal arriving while one is still open is deferred — its
    own `ActionEvent` is still logged as normal (the Router logs every
    proposal unconditionally), it simply never gets a `PendingAction` of
    its own until the first one resolves or expires. The Conversation
    Manager should never have to guess which of two open questions a
    guest's "yes" answers.

    Only proposals with a real guest-facing yes/no question create a row
    here — as of this table's introduction, that's `OFFER_PROPOSED`
    (Revenue Agent) only. `ORDER_PROPOSED` (Ordering Agent v0) and
    `MEMORY_PROPOSED` (Guest Memory Agent) are informational/passive
    today, not a question awaiting an answer, so they never create one
    (see `conversation_manager.py`'s own `_CONFIRMABLE_ACTION_TYPES`).

    `payload`/`origin_agent` (MENU_ORDERING.md §7.1) generalize this
    table to a second, earlier use: tracking a multi-turn proposal
    that's still being *assembled*, not just one already complete and
    awaiting yes/no. `payload` is a JSON blob whose shape is owned
    entirely by whichever agent created it — this table only ever
    inspects one shared convention, a top-level `"complete": bool` —
    and `origin_agent` names which agent's `clarify()` (the
    `ClarifiableAgent` protocol, `agent_protocol.py`) a non-final reply
    gets dispatched back to. Both are `None` for the existing
    confirm/cancel-only flows (Revenue Agent's offers), which never
    need them. `origin_action_type` is nullable for the same reason: a
    cart under construction hasn't been proposed yet, so no
    `ActionEvent` exists for it at all — `origin_action_type` stays
    `None` for as long as `payload["complete"] is False`, and is only
    set once the cart is complete and its `ActionEvent` is finally
    logged.
    """

    __tablename__ = "pending_actions"
    __table_args__ = (
        Index("ix_pending_action_tenant_id", "tenant_id"),
        Index("ix_pending_action_guest_id", "guest_id"),
        Index("ix_pending_action_correlation_id", "correlation_id"),
        # The lookup ConversationManager runs on every inbound message:
        # "is there an active PendingAction for this guest?"
        Index("ix_pending_action_guest_status", "guest_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"))
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    correlation_id: Mapped[str] = mapped_column(String(36))
    # Nullable (MENU_ORDERING.md §7.1): `None` while a cart is still
    # being assembled and no `ActionEvent` has been logged for it yet;
    # set to the real action_type (e.g. "ORDER_PROPOSED") the turn the
    # proposal first becomes complete.
    origin_action_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Copy of the triggering event's own `intent` — so a later
    # ACCEPTED/REJECTED/EXPIRED event can log the same `intent` as the
    # original proposal without ConversationManager needing to guess it
    # from `origin_action_type` (a hardcoded action_type -> intent map
    # would silently go stale the moment a second confirmable
    # action_type is added).
    origin_intent: Mapped[str] = mapped_column(String(32))

    # Which agent's `clarify()` a non-final reply gets dispatched back
    # to (MENU_ORDERING.md §7.2) — `None` for the existing
    # confirm/cancel-only flows, which never need dispatch-back.
    origin_agent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Opaque JSON, shape owned by `origin_agent` — the one convention
    # every caller may rely on is a top-level `"complete": bool`
    # (MENU_ORDERING.md §7.1).
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[PendingActionStatus] = mapped_column(
        Enum(PendingActionStatus), default=PendingActionStatus.pending
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class OrderStatus(str, enum.Enum):
    confirmed = "confirmed"
    received = "received"
    preparing = "preparing"
    delivered = "delivered"
    cancelled = "cancelled"


class Order(Base):
    """A guest's confirmed room-service order — MENU_ORDERING.md §6, the
    durable, confirmed business object. Created ONLY at
    `ORDER_CONFIRMED` (`conversation_manager.py`'s resolve(), not yet
    built), never at `ORDER_PROPOSED` — a cart being assembled or
    awaiting confirmation exists only as `PendingAction.payload` (§7),
    disposable if the guest never confirms. An abandoned cart must
    never look like a business transaction in the data Argus eventually
    learns from, so no row here ever starts out as anything but already
    confirmed — there is deliberately no `pending_confirmation` status;
    that phase belongs to `PendingAction`, not `Order`.

    `correlation_id` is shared with the `ORDER_PROPOSED` `ActionEvent`
    that preceded it, minted when the cart itself was first started
    (`PendingAction.correlation_id`, §7) — the same id threads guest
    intent -> proposal -> confirmation -> this row -> staff execution,
    so the whole lifecycle stays reconstructable from `ActionEvent`
    alone even though this table is a second, durable copy of the
    outcome.
    """

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_order_tenant_id", "tenant_id"),
        Index("ix_order_guest_id", "guest_id"),
        Index("ix_order_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"))
    guest_id: Mapped[str] = mapped_column(ForeignKey("guests.id"))
    reservation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reservations.id"), nullable=True
    )

    correlation_id: Mapped[str] = mapped_column(String(36))

    # Provenance mirroring MenuItem's own `source_import_id` — which
    # upload the ordered items originally came from. Nullable for the
    # same reason MenuItem's is: a future "add one item by hand" path
    # would have no import to point to.
    source_menu_import_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("import_sessions.id"), nullable=True
    )

    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.confirmed)

    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="EUR")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    """One line of a confirmed `Order` — MENU_ORDERING.md §6.
    `name`/`price`/`currency` are snapshotted at confirmation time so a
    later `MenuItem` price edit never retroactively changes what a
    guest already agreed to; `menu_item_id` is kept alongside the
    snapshot (not instead of it) so "show me every order of this dish"
    stays queryable. This snapshot is only meaningful because
    `MenuItem.id` itself is guaranteed stable across edits (Menu
    Importer's own contract, `menu_importer.py`).
    """

    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_item_order_id", "order_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    menu_item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))

    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    order: Mapped["Order"] = relationship("Order", back_populates="items")


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


class ImportSessionStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    failed = "failed"


class ImportSession(Base):
    """One row per import run (manual entry counts as a 1-row import).

    Every importer (manual, CSV, and future PDF/email/PMS connectors) creates
    one of these before writing any Guest/Reservation rows, and every
    Reservation it creates references it via `import_session_id`. This is
    what makes import history, per-source auditing, and future retry-failed-
    rows support possible without each importer inventing its own tracking.
    """

    __tablename__ = "import_sessions"
    __table_args__ = (Index("ix_import_session_tenant_source", "tenant_id", "source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    source: Mapped[str] = mapped_column(String(64))
    status: Mapped[ImportSessionStatus] = mapped_column(
        Enum(ImportSessionStatus), default=ImportSessionStatus.running
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    initiated_by: Mapped[str] = mapped_column(String(255))
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    validation_issues: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


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
