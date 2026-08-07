"""Context Builder — CONCIERGE.md §4, Week 1 remaining step 1.

No AI, no routing, no escalation here — just verifying the one thing
this layer is responsible for: assembling a correct, tenant-isolated
`ConciergeContext` (or refusing to, loudly, when it can't).
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    Guest,
    Message,
    MessageChannel,
    MessageStatus,
    Offer,
    Property,
    PropertyKnowledgeBase,
    Reservation,
    ReservationStatus,
    Tenant,
    Workflow,
)
from app.services.context_builder import ContextBuilder, ContextBuilderError


@pytest.fixture(autouse=True)
def _clear_context_cache():
    # The cache is process-wide (class-level) by design (CONCIERGE.md
    # §4's caching requirement) — clear it around every test so tests
    # can't leak state into each other via stale cached contexts.
    ContextBuilder.clear_cache()
    yield
    ContextBuilder.clear_cache()


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_property(db, *, tenant_id, phone_number_id="PHONE_X"):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(
        tenant_id=tenant_id,
        name=f"{tenant_id} Hotel",
        city="Berlin",
        country="Germany",
        whatsapp_phone_number_id=phone_number_id,
    )
    db.add(property_)
    db.flush()
    return property_


def _make_guest(db, *, tenant_id, property_id, name="Guest", phone="+15550000000"):
    guest = Guest(tenant_id=tenant_id, property_id=property_id, name=name, phone=phone)
    db.add(guest)
    db.flush()
    return guest


def _make_reservation(db, *, tenant_id, property_id, guest_id, status, check_in, check_out):
    reservation = Reservation(
        tenant_id=tenant_id,
        property_id=property_id,
        guest_id=guest_id,
        status=status,
        check_in=check_in,
        check_out=check_out,
    )
    db.add(reservation)
    db.flush()
    return reservation


def test_complete_context_for_checked_in_guest(db_session):
    from datetime import date, timedelta

    db = db_session
    property_ = _make_property(db, tenant_id="hotel-checked-in")
    guest = _make_guest(db, tenant_id="hotel-checked-in", property_id=property_.id)
    reservation = _make_reservation(
        db,
        tenant_id="hotel-checked-in",
        property_id=property_.id,
        guest_id=guest.id,
        status=ReservationStatus.checked_in,
        check_in=date.today() - timedelta(days=1),
        check_out=date.today() + timedelta(days=2),
    )
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id,
            tenant_id="hotel-checked-in",
            wifi_password="guestwifi123",
        )
    )
    db.add(
        Message(
            tenant_id="hotel-checked-in",
            guest_id=guest.id,
            channel=MessageChannel.whatsapp,
            direction="inbound",
            body="What time is breakfast?",
            status=MessageStatus.delivered,
        )
    )
    db.add(
        Workflow(
            tenant_id="hotel-checked-in",
            name="Pre-arrival welcome",
            trigger_event="reservation_confirmed",
            status="active",
        )
    )
    db.flush()

    context = ContextBuilder(db).build(tenant_id="hotel-checked-in", guest_id=guest.id)

    assert context.tenant_id == "hotel-checked-in"
    assert context.property.id == property_.id
    assert context.guest.id == guest.id
    assert context.reservation is not None
    assert context.reservation.id == reservation.id
    assert context.reservation.status == "checked_in"
    assert context.knowledge_base is not None
    assert context.knowledge_base.wifi_password == "guestwifi123"
    assert len(context.conversation_history) == 1
    assert context.conversation_history[0].body == "What time is breakfast?"
    assert len(context.available_automations) == 1
    assert context.available_automations[0].trigger_event == "reservation_confirmed"
    assert context.channel.phone_number_id == "PHONE_X"


def test_guest_with_no_active_reservation(db_session):
    from datetime import date, timedelta

    db = db_session
    property_ = _make_property(db, tenant_id="hotel-no-active")
    guest = _make_guest(db, tenant_id="hotel-no-active", property_id=property_.id)
    # Only a past, checked-out stay — nothing active or upcoming.
    _make_reservation(
        db,
        tenant_id="hotel-no-active",
        property_id=property_.id,
        guest_id=guest.id,
        status=ReservationStatus.checked_out,
        check_in=date.today() - timedelta(days=30),
        check_out=date.today() - timedelta(days=28),
    )
    db.flush()

    context = ContextBuilder(db).build(tenant_id="hotel-no-active", guest_id=guest.id)

    assert context.reservation is None
    assert context.guest.id == guest.id  # rest of context still assembles fine


def test_unknown_guest_raises(db_session):
    db = db_session
    _make_property(db, tenant_id="hotel-unknown-guest")
    db.flush()

    with pytest.raises(ContextBuilderError):
        ContextBuilder(db).build(tenant_id="hotel-unknown-guest", guest_id="no-such-guest")


def test_missing_knowledge_base_is_none_not_an_error(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-no-kb")
    guest = _make_guest(db, tenant_id="hotel-no-kb", property_id=property_.id)
    db.flush()

    context = ContextBuilder(db).build(tenant_id="hotel-no-kb", guest_id=guest.id)

    assert context.knowledge_base is None


def test_multi_tenant_isolation_no_cross_property_leakage(db_session):
    db = db_session
    property_a = _make_property(db, tenant_id="hotel-iso-a", phone_number_id="PHONE_A")
    guest_a = _make_guest(db, tenant_id="hotel-iso-a", property_id=property_a.id, name="Guest A")
    property_b = _make_property(db, tenant_id="hotel-iso-b", phone_number_id="PHONE_B")
    _make_guest(db, tenant_id="hotel-iso-b", property_id=property_b.id, name="Guest B")
    db.flush()

    # Guest A's real ID, but asking for it under tenant B — must not
    # resolve to Guest A's data under the wrong tenant.
    with pytest.raises(ContextBuilderError):
        ContextBuilder(db).build(tenant_id="hotel-iso-b", guest_id=guest_a.id)

    # And the correct tenant still gets its own data cleanly.
    context = ContextBuilder(db).build(tenant_id="hotel-iso-a", guest_id=guest_a.id)
    assert context.property.id == property_a.id
    assert context.channel.phone_number_id == "PHONE_A"


def test_cache_hit_avoids_rebuilding(db_session, monkeypatch):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-cache-hit")
    guest = _make_guest(db, tenant_id="hotel-cache-hit", property_id=property_.id)
    db.flush()

    builder = ContextBuilder(db, cache_ttl_seconds=30.0)
    first = builder.build(tenant_id="hotel-cache-hit", guest_id=guest.id)

    calls = {"count": 0}
    original = ContextBuilder._build_uncached

    def counting_build(self, **kwargs):
        calls["count"] += 1
        return original(self, **kwargs)

    monkeypatch.setattr(ContextBuilder, "_build_uncached", counting_build)

    second = builder.build(tenant_id="hotel-cache-hit", guest_id=guest.id)

    assert calls["count"] == 0  # served from cache, never rebuilt
    assert second is first  # same cached object, not just equal data


def test_cache_expires_after_ttl(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-cache-expiry")
    guest = _make_guest(db, tenant_id="hotel-cache-expiry", property_id=property_.id)
    db.flush()

    builder = ContextBuilder(db, cache_ttl_seconds=0.05)
    first = builder.build(tenant_id="hotel-cache-expiry", guest_id=guest.id)
    time.sleep(0.1)
    second = builder.build(tenant_id="hotel-cache-expiry", guest_id=guest.id)

    assert second is not first  # rebuilt, not served from an expired entry
    assert second.guest.id == first.guest.id  # still correct data either way
