"""Ordering Agent persistence layer — MENU_ORDERING.md §6/§7.1, the
first implementation slice of the frozen design (PR #27). Schema-level
tests only: the `PendingAction` extension (`payload`, `origin_agent`,
nullable `origin_action_type`) and the new `Order`/`OrderItem` models.

No agent behavior is exercised here — `ClarifiableAgent` has no
implementer yet, and Conversation Manager's dispatch-back mode isn't
wired in this slice (MENU_ORDERING.md §17 step 6-10 continues in a
follow-up PR). These tests exist to lock the persistence contract the
rest of that work builds against, mirroring how test_menu_importer.py
locked MenuItem's own contract ahead of the editor endpoint.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    Guest,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    PendingAction,
    PendingActionStatus,
    Property,
    Tenant,
)


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


def _make_guest(db, *, tenant_id="demo-hotel"):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name="Demo Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest")
    db.add(guest)
    db.flush()
    return guest, property_


def _make_menu_item(db, *, tenant_id, property_id):
    item = MenuItem(
        tenant_id=tenant_id, property_id=property_id, menu_name="Room Service",
        name="Club Sandwich", price=18.0, currency="EUR",
    )
    db.add(item)
    db.flush()
    return item


# ---------------------------------------------------------------------------
# PendingAction schema extension (§7.1)
# ---------------------------------------------------------------------------


def test_pending_action_can_be_created_with_incomplete_cart_and_no_origin_action_type(db_session):
    """A cart under construction has no ActionEvent yet, so
    origin_action_type must be able to stay None (§7.1/§7.3)."""
    guest, _ = _make_guest(db_session)
    payload = {"complete": False, "cart": [], "unresolved": {"item": "burger"}}

    pending = PendingAction(
        tenant_id=guest.tenant_id,
        guest_id=guest.id,
        correlation_id="corr-1",
        origin_action_type=None,
        origin_intent="ordering",
        origin_agent="ordering",
        payload=json.dumps(payload),
        status=PendingActionStatus.pending,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db_session.add(pending)
    db_session.commit()
    db_session.refresh(pending)

    assert pending.origin_action_type is None
    assert pending.origin_agent == "ordering"
    assert json.loads(pending.payload)["complete"] is False


def test_pending_action_origin_action_type_still_settable_once_cart_completes(db_session):
    """Once the cart becomes complete, origin_action_type is set to the
    real action_type (§7.1) — the same row, updated in place."""
    guest, _ = _make_guest(db_session)
    pending = PendingAction(
        tenant_id=guest.tenant_id,
        guest_id=guest.id,
        correlation_id="corr-2",
        origin_action_type=None,
        origin_intent="ordering",
        origin_agent="ordering",
        payload=json.dumps({"complete": False, "cart": []}),
        status=PendingActionStatus.pending,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db_session.add(pending)
    db_session.commit()

    pending.origin_action_type = "ORDER_PROPOSED"
    pending.payload = json.dumps({"complete": True, "cart": [{"menu_item_id": "x"}]})
    db_session.commit()
    db_session.refresh(pending)

    assert pending.origin_action_type == "ORDER_PROPOSED"
    assert json.loads(pending.payload)["complete"] is True


def test_pending_action_payload_and_origin_agent_default_to_none_for_existing_flows(db_session):
    """Revenue Agent's confirm/cancel-only flow never sets these — they
    must default to None without every existing call site changing."""
    guest, _ = _make_guest(db_session)
    pending = PendingAction(
        tenant_id=guest.tenant_id,
        guest_id=guest.id,
        correlation_id="corr-3",
        origin_action_type="OFFER_PROPOSED",
        origin_intent="revenue_upsell",
        status=PendingActionStatus.pending,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db_session.add(pending)
    db_session.commit()
    db_session.refresh(pending)

    assert pending.origin_agent is None
    assert pending.payload is None


# ---------------------------------------------------------------------------
# Order / OrderItem (§6)
# ---------------------------------------------------------------------------


def test_order_created_with_snapshotted_items(db_session):
    guest, property_ = _make_guest(db_session)
    menu_item = _make_menu_item(db_session, tenant_id=guest.tenant_id, property_id=property_.id)

    order = Order(
        tenant_id=guest.tenant_id,
        property_id=property_.id,
        guest_id=guest.id,
        correlation_id="corr-4",
        total_amount=36.0,
        currency="EUR",
        status=OrderStatus.confirmed,
    )
    order.items.append(
        OrderItem(
            menu_item_id=menu_item.id,
            name=menu_item.name,
            price=menu_item.price,
            currency=menu_item.currency,
            quantity=2,
        )
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    assert order.status == OrderStatus.confirmed
    assert len(order.items) == 1
    assert order.items[0].name == "Club Sandwich"
    assert order.items[0].quantity == 2


def test_order_status_has_no_pending_confirmation_state():
    """§6: an Order only ever starts out already-confirmed — that phase
    belongs to PendingAction, not Order."""
    assert "pending_confirmation" not in [s.value for s in OrderStatus]
    assert {s.value for s in OrderStatus} == {
        "confirmed", "received", "preparing", "delivered", "cancelled",
    }


def test_order_item_survives_a_later_menu_item_price_edit(db_session):
    """The snapshot must not retroactively change when MenuItem.price
    is edited later — that's the whole point of snapshotting (§6)."""
    guest, property_ = _make_guest(db_session)
    menu_item = _make_menu_item(db_session, tenant_id=guest.tenant_id, property_id=property_.id)

    order = Order(
        tenant_id=guest.tenant_id, property_id=property_.id, guest_id=guest.id,
        correlation_id="corr-5", total_amount=18.0, currency="EUR",
    )
    order.items.append(
        OrderItem(
            menu_item_id=menu_item.id, name=menu_item.name,
            price=menu_item.price, currency=menu_item.currency, quantity=1,
        )
    )
    db_session.add(order)
    db_session.commit()

    menu_item.price = 25.0
    db_session.commit()
    db_session.refresh(order)

    assert float(order.items[0].price) == 18.0
    assert menu_item.price == 25.0
