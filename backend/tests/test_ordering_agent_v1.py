"""Ordering Agent v1 — MENU_ORDERING.md §6/§7, the real cart-building
layer on top of `context.menu_items` (see `ordering_agent.py`'s own
module docstring for the full contract). `test_ordering_agent.py`
keeps v0's triage-only coverage (no menu configured, or a generic
hunger phrase); this file covers everything that only exists once a
menu is populated: item recognition, quantity/variant clarification,
and the confirmation-time `Order`/`OrderItem` snapshot.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import Guest, Order, OrderItem, PendingAction, Property, Tenant
from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    MenuItemContext,
    PropertyContext,
)
from app.services.ordering_agent import ordering_agent, on_order_confirmed


def _menu_item(id_, name, price=12.0, currency="EUR", **kwargs):
    return MenuItemContext(
        id=id_, menu_name="Room Service", name=name, price=price, currency=currency,
        vegetarian=kwargs.get("vegetarian", False), vegan=kwargs.get("vegan", False),
        gluten_free=kwargs.get("gluten_free", False), spicy=kwargs.get("spicy", False),
    )


def _make_context(menu_items=None, **overrides) -> ConciergeContext:
    defaults = dict(
        tenant_id="hotel-x",
        property=PropertyContext(
            id="prop-1", name="Hotel X", timezone="UTC", currency="EUR", brand_voice="Warm"
        ),
        guest=GuestContext(
            id="guest-1", name="Guest", language="en", communication_preference="whatsapp",
            stay_count=1, lifetime_spend=0.0, previous_reviews=0, complaint_history=0,
            upsell_acceptance=0.0,
        ),
        current_time=datetime.utcnow(),
        channel=ChannelMetadata(channel="whatsapp"),
        menu_items=menu_items or [],
    )
    defaults.update(overrides)
    return ConciergeContext(**defaults)


# ---------------------------------------------------------------------------
# answer() -- first turn
# ---------------------------------------------------------------------------


def test_unambiguous_item_with_quantity_is_complete_on_first_turn():
    context = _make_context(menu_items=[_menu_item("mi-1", "Chicken Biryani", price=12.0)])

    response = ordering_agent.answer(context, "Two chicken biryani please")

    assert response.handled is True
    assert response.should_escalate is False
    payload = response.metadata["payload"]
    assert payload["complete"] is True
    assert payload["cart"] == [
        {"menu_item_id": "mi-1", "name": "Chicken Biryani", "price": 12.0, "currency": "EUR", "quantity": 2}
    ]
    assert response.metadata["action_type"] == "ORDER_PROPOSED"


def test_multiple_items_in_one_message():
    context = _make_context(
        menu_items=[
            _menu_item("mi-1", "Chicken Biryani", price=12.0),
            _menu_item("mi-2", "Club Sandwich", price=9.0),
        ]
    )

    response = ordering_agent.answer(context, "One club sandwich and two chicken biryani")

    payload = response.metadata["payload"]
    assert payload["complete"] is True
    names_and_qty = {(line["name"], line["quantity"]) for line in payload["cart"]}
    assert names_and_qty == {("Club Sandwich", 1), ("Chicken Biryani", 2)}


def test_missing_quantity_asks_for_clarification():
    context = _make_context(menu_items=[_menu_item("mi-1", "Chicken Biryani")])

    response = ordering_agent.answer(context, "Chicken biryani please")

    payload = response.metadata["payload"]
    assert payload["complete"] is False
    assert payload["unresolved"] == {
        "type": "quantity", "menu_item_id": "mi-1", "name": "Chicken Biryani",
        "price": 12.0, "currency": "EUR",
    }
    assert "action_type" not in response.metadata
    assert "how many" in response.response.lower()


def test_ambiguous_variant_asks_which_one():
    context = _make_context(
        menu_items=[
            _menu_item("mi-1", "Chicken Biryani (Spicy)"),
            _menu_item("mi-2", "Chicken Biryani (Mild)"),
        ]
    )

    response = ordering_agent.answer(context, "I'd like the chicken biryani")

    payload = response.metadata["payload"]
    assert payload["complete"] is False
    assert payload["unresolved"]["type"] == "choice"
    candidate_names = {c["name"] for c in payload["unresolved"]["candidates"]}
    assert candidate_names == {"Chicken Biryani (Spicy)", "Chicken Biryani (Mild)"}


def test_unmatched_phrase_never_invents_a_recommendation_falls_back_to_handoff():
    """'Get me something healthy' matches nothing on the menu by name —
    must never be turned into an invented recommendation, falls through
    to the same v0 hand-off/escalate path as a generic hunger phrase."""
    context = _make_context(menu_items=[_menu_item("mi-1", "Chicken Biryani")])

    response = ordering_agent.answer(context, "I'm hungry, get me something healthy")

    assert "payload" not in response.metadata
    assert response.metadata["handoff"] is None
    assert response.should_escalate is True


def test_no_menu_configured_uses_v0_handoff_unchanged():
    """With no `MenuItem` catalog to match against, a bare dish-name
    mention alone isn't a recognized food signal -- only v0's own
    hunger phrasing still reaches this agent at all."""
    context = _make_context(menu_items=[])
    response = ordering_agent.answer(context, "I'm hungry")
    assert "payload" not in response.metadata
    assert response.should_escalate is True  # nothing configured at all


# ---------------------------------------------------------------------------
# clarify() -- second turn
# ---------------------------------------------------------------------------


def test_clarify_resolves_quantity_and_completes_cart():
    context = _make_context(menu_items=[_menu_item("mi-1", "Chicken Biryani")])
    first = ordering_agent.answer(context, "Chicken biryani please")
    payload = first.metadata["payload"]

    response = ordering_agent.clarify(context, "two please", payload)

    assert response.handled is True
    new_payload = response.metadata["payload"]
    assert new_payload["complete"] is True
    assert new_payload["cart"] == [
        {"menu_item_id": "mi-1", "name": "Chicken Biryani", "price": 12.0, "currency": "EUR", "quantity": 2}
    ]
    assert response.metadata["action_type"] == "ORDER_PROPOSED"


def test_clarify_resolves_ambiguous_choice_defaults_quantity_to_one():
    context = _make_context(
        menu_items=[
            _menu_item("mi-1", "Chicken Biryani (Spicy)"),
            _menu_item("mi-2", "Chicken Biryani (Mild)"),
        ]
    )
    first = ordering_agent.answer(context, "I'd like the chicken biryani")
    payload = first.metadata["payload"]

    response = ordering_agent.clarify(context, "the spicy one please", payload)

    new_payload = response.metadata["payload"]
    assert new_payload["complete"] is True
    assert new_payload["cart"] == [
        {"menu_item_id": "mi-1", "name": "Chicken Biryani (Spicy)", "price": 12.0, "currency": "EUR", "quantity": 1}
    ]


def test_clarify_unresolvable_reply_escalates_without_payload():
    context = _make_context(menu_items=[_menu_item("mi-1", "Chicken Biryani")])
    first = ordering_agent.answer(context, "Chicken biryani please")
    payload = first.metadata["payload"]

    response = ordering_agent.clarify(context, "asdkjh nonsense", payload)

    assert response.should_escalate is True
    assert "payload" not in response.metadata


# ---------------------------------------------------------------------------
# on_order_confirmed -- the Order/OrderItem snapshot
# ---------------------------------------------------------------------------


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


def test_on_order_confirmed_creates_order_and_snapshotted_items(db_session):
    db = db_session
    db.add(Tenant(id="hotel-y", name="hotel-y"))
    property_ = Property(tenant_id="hotel-y", name="Hotel Y", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id="hotel-y", property_id=property_.id, name="Guest")
    db.add(guest)
    db.flush()

    pending = PendingAction(
        tenant_id="hotel-y", guest_id=guest.id, correlation_id="corr-1",
        origin_action_type="ORDER_PROPOSED", origin_intent="order", origin_agent="ordering",
        payload="{}",
        expires_at=datetime.utcnow(),
    )
    db.add(pending)
    db.flush()

    context = _make_context(tenant_id="hotel-y", property=PropertyContext(
        id=property_.id, name="Hotel Y", timezone="UTC", currency="EUR", brand_voice="Warm"
    ))
    payload = {
        "cart": [
            {"menu_item_id": "mi-1", "name": "Chicken Biryani", "price": 12.0, "currency": "EUR", "quantity": 2},
        ]
    }

    result = on_order_confirmed(db, context, pending, payload)

    assert result is not None
    order = db.query(Order).filter(Order.id == result["order_id"]).one()
    assert order.tenant_id == "hotel-y"
    assert order.guest_id == guest.id
    assert order.correlation_id == "corr-1"
    assert float(order.total_amount) == 24.0
    assert order.currency == "EUR"

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    assert len(items) == 1
    assert items[0].name == "Chicken Biryani"
    assert items[0].quantity == 2


def test_on_order_confirmed_is_a_noop_for_an_empty_cart(db_session):
    db = db_session
    db.add(Tenant(id="hotel-z", name="hotel-z"))
    property_ = Property(tenant_id="hotel-z", name="Hotel Z", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id="hotel-z", property_id=property_.id, name="Guest")
    db.add(guest)
    db.flush()
    pending = PendingAction(
        tenant_id="hotel-z", guest_id=guest.id, correlation_id="corr-2",
        origin_action_type="ORDER_PROPOSED", origin_intent="order",
        expires_at=datetime.utcnow(),
    )
    db.add(pending)
    db.flush()
    context = _make_context(tenant_id="hotel-z")

    result = on_order_confirmed(db, context, pending, {})

    assert result is None
    assert db.query(Order).count() == 0
