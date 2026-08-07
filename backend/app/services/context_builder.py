"""Context Builder — CONCIERGE.md §4, Week 1 remaining step 1.

The single object every future Concierge agent (FAQ, Guest Memory,
Revenue) will read from — assembled once per turn, never mutated, and
no agent queries the database directly. This module owns 100% of the
data access for the Concierge feature; everything downstream only ever
reads a `ConciergeContext`.

Deliberately excluded here (per explicit scope for this step): LLM
calls, routing, escalation, FAQ answering, revenue offers, Guest Memory
writes. This file's only job is assembling context.

    WhatsApp -> Tenant Routing -> Context Builder -> ConciergeContext

No AI is involved yet.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.entities import (
    Guest,
    Message,
    MessageChannel,
    Offer,
    Property,
    PropertyKnowledgeBase,
    Reservation,
    ReservationStatus,
    Workflow,
)

# How many recent messages count as "conversation history" — a fixed
# point inside the 20-50 range CONCIERGE.md called for. Not configurable
# per call: every agent should see the same amount of history for the
# same conversation, or "did the agent forget something" becomes
# ambiguous between "wasn't in context" and "context size differed".
CONVERSATION_HISTORY_LIMIT = 30

# Cache TTL: long enough that a guest's back-to-back messages within one
# exchange don't each re-hit the database for Property/Guest/Knowledge
# Base rows that didn't change; short enough that a hotel updating its
# Knowledge Base, or a new inbound message landing, becomes visible on
# the next real turn rather than being stuck behind a stale read for
# minutes. Conversation history specifically can go stale for up to this
# TTL mid-burst — an accepted tradeoff (CONCIERGE.md §4's Context
# Builder is the data-assembly layer; a turn's own just-received message
# is handled by the caller directly, not solely through this cache).
DEFAULT_CACHE_TTL_SECONDS = 45.0


class ContextBuilderError(ValueError):
    """Base class for Context Builder failures — a tenant/guest/
    reservation that doesn't exist or doesn't belong together. Never
    silently substitutes a different tenant's data; always raises."""


class PropertyContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    timezone: str
    currency: str
    brand_voice: str
    whatsapp_phone_number_id: Optional[str] = None


class GuestContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    language: str
    communication_preference: str
    preferred_room: Optional[str] = None
    dietary_preferences: Optional[str] = None
    birthday: Optional[date] = None
    anniversary: Optional[date] = None
    notes: Optional[str] = None
    # "Loyalty status" isn't a stored category — these are the raw
    # signals that make one up. Deriving a label ("Gold"/"Regular") is
    # an agent's job, not this layer's; exposing a fabricated category
    # here would be inventing data the schema doesn't have.
    stay_count: int
    lifetime_spend: float
    previous_reviews: int
    complaint_history: int
    upsell_acceptance: float


class ReservationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: str
    room_type: str
    check_in: date
    check_out: date
    adults: int
    children: int
    special_requests: Optional[str] = None


class KnowledgeBaseContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    wifi_password: Optional[str] = None
    breakfast_hours: Optional[str] = None
    pool_hours: Optional[str] = None
    gym_hours: Optional[str] = None
    spa_hours: Optional[str] = None
    parking_info: Optional[str] = None
    checkin_time: Optional[str] = None
    checkout_time: Optional[str] = None
    late_checkout_policy: Optional[str] = None
    airport_transfer_info: Optional[str] = None
    pet_policy: Optional[str] = None
    house_rules: Optional[str] = None
    policies: Optional[str] = None
    restaurants: Optional[str] = None
    cafes: Optional[str] = None
    nearby_attractions: Optional[str] = None
    services: Optional[str] = None
    room_service_hours: Optional[str] = None
    emergency_contacts: Optional[str] = None


class ConversationMessageContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    direction: str
    channel: str
    message_type: str
    body: str
    created_at: datetime


class PreviousOfferContext(BaseModel):
    """Part of "Previous AI Actions" — read from existing Offer data,
    no new tracking table (CONCIERGE.md §6)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    category: str
    status: str
    price: float
    currency: str
    created_at: datetime


class AutomationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    trigger_event: str


class ChannelMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: str
    phone_number_id: Optional[str] = None
    conversation_id: Optional[str] = None


class ConciergeContext(BaseModel):
    """The one object every agent reads from. Frozen — an agent that
    tries to mutate it raises, the same way a bad SQL query would; this
    is enforced, not just documented."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    property: PropertyContext
    guest: GuestContext
    reservation: Optional[ReservationContext] = None
    conversation_history: list[ConversationMessageContext] = []
    previous_offers: list[PreviousOfferContext] = []
    knowledge_base: Optional[KnowledgeBaseContext] = None
    current_time: datetime
    available_automations: list[AutomationContext] = []
    channel: ChannelMetadata


class _CacheEntry(BaseModel):
    expires_at: float
    context: ConciergeContext


class ContextBuilder:
    """Assembles a `ConciergeContext`. One instance per request/db
    session is the expected usage; the cache itself is process-wide
    (module-level) so it still helps across instances within the same
    process. A multi-instance deployment would need this to move to
    Redis (already available via `settings.redis_url`) instead of an
    in-process dict — not needed at current scale, called out here so
    it isn't a silent surprise later.
    """

    _cache: dict[tuple[str, str, Optional[str]], _CacheEntry] = {}

    def __init__(self, db: Session, *, cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS):
        self.db = db
        self.cache_ttl_seconds = cache_ttl_seconds

    def build(
        self,
        *,
        tenant_id: str,
        guest_id: str,
        reservation_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ConciergeContext:
        cache_key = (tenant_id, guest_id, reservation_id)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        context = self._build_uncached(
            tenant_id=tenant_id,
            guest_id=guest_id,
            reservation_id=reservation_id,
            conversation_id=conversation_id,
        )
        self._cache_set(cache_key, context)
        return context

    # -- cache -----------------------------------------------------

    def _cache_get(
        self, key: tuple[str, str, Optional[str]]
    ) -> Optional[ConciergeContext]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._cache.pop(key, None)
            return None
        return entry.context

    def _cache_set(self, key: tuple[str, str, Optional[str]], context: ConciergeContext) -> None:
        self._cache[key] = _CacheEntry(
            expires_at=time.monotonic() + self.cache_ttl_seconds, context=context
        )

    @classmethod
    def clear_cache(cls) -> None:
        """Test/ops escape hatch — not called from normal request flow."""
        cls._cache.clear()

    @classmethod
    def invalidate_tenant(cls, tenant_id: str) -> None:
        """Evicts every cached context for one tenant, regardless of
        which guest/reservation it was keyed under. Knowledge Base data
        is per-property, not per-guest, so a KB edit invalidates every
        guest's cached context for that tenant, not just one.

        **Contract**: anything that writes to `PropertyKnowledgeBase` (or
        any other property-wide fact this Context Builder reads —
        `Property` itself, `Workflow` automations) MUST call this after
        committing the write. There is no KB editor yet (only the model,
        PR #12) — this exists so the editor has the right hook to call
        from day one instead of the TTL being the only thing standing
        between an edit and a guest getting a stale answer for up to
        `cache_ttl_seconds`.
        """
        stale_keys = [key for key in cls._cache if key[0] == tenant_id]
        for key in stale_keys:
            cls._cache.pop(key, None)

    # -- assembly ----------------------------------------------------

    def _build_uncached(
        self,
        *,
        tenant_id: str,
        guest_id: str,
        reservation_id: Optional[str],
        conversation_id: Optional[str],
    ) -> ConciergeContext:
        guest = (
            self.db.query(Guest)
            .filter(Guest.id == guest_id, Guest.tenant_id == tenant_id)
            .first()
        )
        if guest is None:
            raise ContextBuilderError(
                f"Guest {guest_id} not found for tenant {tenant_id} — refusing to "
                "build context rather than guess or substitute another guest"
            )

        property_ = (
            self.db.query(Property)
            .filter(Property.id == guest.property_id, Property.tenant_id == tenant_id)
            .first()
        )
        if property_ is None:
            raise ContextBuilderError(
                f"Property for guest {guest_id} not found under tenant {tenant_id}"
            )

        reservation = self._resolve_reservation(
            tenant_id=tenant_id, guest_id=guest_id, reservation_id=reservation_id
        )
        knowledge_base = self._load_knowledge_base(property_.id, tenant_id)
        conversation_history = self._load_conversation_history(
            tenant_id=tenant_id, guest_id=guest_id
        )
        previous_offers = self._load_previous_offers(tenant_id=tenant_id, guest_id=guest_id)
        automations = self._load_available_automations(tenant_id)

        return ConciergeContext(
            tenant_id=tenant_id,
            property=PropertyContext(
                id=property_.id,
                name=property_.name,
                timezone=property_.timezone,
                currency=property_.currency,
                brand_voice=property_.brand_voice,
                whatsapp_phone_number_id=property_.whatsapp_phone_number_id,
            ),
            guest=GuestContext(
                id=guest.id,
                name=guest.name,
                email=guest.email,
                phone=guest.phone,
                language=guest.language,
                communication_preference=guest.communication_preference,
                preferred_room=guest.preferred_room,
                dietary_preferences=guest.dietary_preferences,
                birthday=guest.birthday,
                anniversary=guest.anniversary,
                notes=guest.notes,
                stay_count=guest.stay_count,
                lifetime_spend=float(guest.lifetime_spend or 0),
                previous_reviews=guest.previous_reviews,
                complaint_history=guest.complaint_history,
                upsell_acceptance=guest.upsell_acceptance,
            ),
            reservation=reservation,
            conversation_history=conversation_history,
            previous_offers=previous_offers,
            knowledge_base=knowledge_base,
            current_time=datetime.utcnow(),
            available_automations=automations,
            channel=ChannelMetadata(
                channel="whatsapp",
                phone_number_id=property_.whatsapp_phone_number_id,
                conversation_id=conversation_id,
            ),
        )

    def _resolve_reservation(
        self, *, tenant_id: str, guest_id: str, reservation_id: Optional[str]
    ) -> Optional[ReservationContext]:
        if reservation_id is not None:
            reservation = (
                self.db.query(Reservation)
                .filter(
                    Reservation.id == reservation_id,
                    Reservation.tenant_id == tenant_id,
                    Reservation.guest_id == guest_id,
                )
                .first()
            )
            if reservation is None:
                raise ContextBuilderError(
                    f"Reservation {reservation_id} not found for guest {guest_id} "
                    f"under tenant {tenant_id} — never substitutes another "
                    "reservation silently"
                )
            return self._to_reservation_context(reservation)

        # No explicit reservation_id: resolve the guest's current/active
        # one, if any. A guest with no active or upcoming stay is a
        # valid state (reservation=None), not an error.
        today = date.today()
        candidates = (
            self.db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.guest_id == guest_id,
                Reservation.status != ReservationStatus.cancelled,
                Reservation.check_out >= today,
            )
            .all()
        )
        if not candidates:
            return None
        candidates.sort(
            key=lambda r: (r.status != ReservationStatus.checked_in, r.check_in)
        )
        return self._to_reservation_context(candidates[0])

    @staticmethod
    def _to_reservation_context(reservation: Reservation) -> ReservationContext:
        return ReservationContext(
            id=reservation.id,
            status=reservation.status.value,
            room_type=reservation.room_type,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            adults=reservation.adults,
            children=reservation.children,
            special_requests=reservation.special_requests,
        )

    def _load_knowledge_base(
        self, property_id: str, tenant_id: str
    ) -> Optional[KnowledgeBaseContext]:
        kb = (
            self.db.query(PropertyKnowledgeBase)
            .filter(
                PropertyKnowledgeBase.property_id == property_id,
                PropertyKnowledgeBase.tenant_id == tenant_id,
            )
            .first()
        )
        if kb is None:
            return None
        return KnowledgeBaseContext(
            wifi_password=kb.wifi_password,
            breakfast_hours=kb.breakfast_hours,
            pool_hours=kb.pool_hours,
            gym_hours=kb.gym_hours,
            spa_hours=kb.spa_hours,
            parking_info=kb.parking_info,
            checkin_time=kb.checkin_time,
            checkout_time=kb.checkout_time,
            late_checkout_policy=kb.late_checkout_policy,
            airport_transfer_info=kb.airport_transfer_info,
            pet_policy=kb.pet_policy,
            house_rules=kb.house_rules,
            policies=kb.policies,
            restaurants=kb.restaurants,
            cafes=kb.cafes,
            nearby_attractions=kb.nearby_attractions,
            services=kb.services,
            room_service_hours=kb.room_service_hours,
            emergency_contacts=kb.emergency_contacts,
        )

    def _load_conversation_history(
        self, *, tenant_id: str, guest_id: str
    ) -> list[ConversationMessageContext]:
        messages = (
            self.db.query(Message)
            .filter(
                Message.tenant_id == tenant_id,
                Message.guest_id == guest_id,
                Message.channel == MessageChannel.whatsapp,
            )
            .order_by(Message.created_at.desc())
            .limit(CONVERSATION_HISTORY_LIMIT)
            .all()
        )
        messages.reverse()  # oldest first, matching how a transcript reads
        return [
            ConversationMessageContext(
                id=m.id,
                direction=m.direction,
                channel=m.channel.value,
                message_type=m.message_type,
                body=m.body,
                created_at=m.sent_at or m.created_at,
            )
            for m in messages
        ]

    def _load_previous_offers(
        self, *, tenant_id: str, guest_id: str
    ) -> list[PreviousOfferContext]:
        offers = (
            self.db.query(Offer)
            .join(Reservation, Offer.reservation_id == Reservation.id)
            .filter(Reservation.tenant_id == tenant_id, Reservation.guest_id == guest_id)
            .order_by(Offer.created_at.desc())
            .limit(CONVERSATION_HISTORY_LIMIT)
            .all()
        )
        return [
            PreviousOfferContext(
                id=o.id,
                name=o.name,
                category=o.category,
                status=o.status.value,
                price=float(o.price or 0),
                currency=o.currency,
                created_at=o.created_at,
            )
            for o in offers
        ]

    def _load_available_automations(self, tenant_id: str) -> list[AutomationContext]:
        workflows = (
            self.db.query(Workflow)
            .filter(Workflow.tenant_id == tenant_id, Workflow.status == "active")
            .all()
        )
        return [
            AutomationContext(id=w.id, name=w.name, trigger_event=w.trigger_event)
            for w in workflows
        ]
