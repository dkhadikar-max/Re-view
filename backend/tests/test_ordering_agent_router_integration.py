"""Ordering Agent v1 — full Router integration (MENU_ORDERING.md
§6/§7). The end-to-end loop this whole build sequence exists for:
guest names a dish -> missing quantity clarified over a second turn ->
`ORDER_PROPOSED` -> guest confirms -> `Order`/`OrderItem` snapshot ->
staff `Task` -> `ORDER_CONFIRMED`/`TASK_CREATED`, all sharing one
`correlation_id`. Real (SQLite, in-memory) database and the full
pipeline — same fixture pattern as
test_conversation_manager_router_integration.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    ActionEvent,
    Guest,
    MenuItem,
    Order,
    OrderItem,
    PendingAction,
    PendingActionStatus,
    Property,
    Task,
    Tenant,
)
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import conversation_manager


@pytest.fixture(autouse=True)
def _clear_context_cache():
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


def _make_property_with_menu(db, *, tenant_id):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    db.add(
        MenuItem(
            tenant_id=tenant_id, property_id=property_.id, menu_name="Room Service",
            name="Chicken Biryani", price=12.0, currency="EUR",
        )
    )
    db.flush()
    return property_


def _make_guest(db, *, tenant_id, property_id):
    guest = Guest(tenant_id=tenant_id, property_id=property_id, name="Guest")
    db.add(guest)
    db.flush()
    return guest


def test_complete_cart_on_first_turn_proposes_immediately(db_session):
    db = db_session
    property_ = _make_property_with_menu(db, tenant_id="hotel-a")
    guest = _make_guest(db, tenant_id="hotel-a", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-a", guest_id=guest.id, message_body="Two chicken biryani please"
    )

    assert response.handled is True
    pending = conversation_manager.find_active(db, tenant_id="hotel-a", guest_id=guest.id)
    assert pending is not None
    assert pending.origin_action_type == "ORDER_PROPOSED"

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-a").all()
    assert [e.action_type for e in events] == ["ORDER_PROPOSED"]


def test_incomplete_cart_starts_clarification_with_no_action_event(db_session):
    db = db_session
    property_ = _make_property_with_menu(db, tenant_id="hotel-b")
    guest = _make_guest(db, tenant_id="hotel-b", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-b", guest_id=guest.id, message_body="Chicken biryani please"
    )

    assert response.handled is True
    assert "how many" in response.response.lower()

    pending = conversation_manager.find_active(db, tenant_id="hotel-b", guest_id=guest.id)
    assert pending is not None
    assert pending.origin_action_type is None
    assert pending.origin_agent == "ordering"

    # Nothing was proposed yet -- no ActionEvent at all.
    assert db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-b").count() == 0


def test_full_loop_clarify_then_confirm_creates_order_and_task(db_session):
    db = db_session
    property_ = _make_property_with_menu(db, tenant_id="hotel-c")
    guest = _make_guest(db, tenant_id="hotel-c", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-c", guest_id=guest.id, message_body="Chicken biryani please")
    pending_incomplete = conversation_manager.find_active(db, tenant_id="hotel-c", guest_id=guest.id)
    correlation_id = pending_incomplete.correlation_id

    clarify_response = concierge_router.route(
        db, tenant_id="hotel-c", guest_id=guest.id, message_body="two please"
    )
    assert "confirm" in clarify_response.response.lower()

    pending_complete = conversation_manager.find_active(db, tenant_id="hotel-c", guest_id=guest.id)
    assert pending_complete.id == pending_incomplete.id  # same row, updated in place
    assert pending_complete.origin_action_type == "ORDER_PROPOSED"
    assert pending_complete.correlation_id == correlation_id

    events_after_propose = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-c").all()
    assert [e.action_type for e in events_after_propose] == ["ORDER_PROPOSED"]

    confirm_response = concierge_router.route(
        db, tenant_id="hotel-c", guest_id=guest.id, message_body="yes, confirm it"
    )
    assert confirm_response.metadata.get("conversation_manager") == "accepted"

    final_pending = db.query(PendingAction).filter(PendingAction.tenant_id == "hotel-c").one()
    assert final_pending.status == PendingActionStatus.resolved
    assert final_pending.correlation_id == correlation_id

    events_final = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-c").all()
    action_types = {e.action_type for e in events_final}
    assert action_types == {"ORDER_PROPOSED", "ORDER_CONFIRMED", "TASK_CREATED"}
    assert all(e.correlation_id == correlation_id for e in events_final)

    order = db.query(Order).filter(Order.tenant_id == "hotel-c").one()
    assert order.guest_id == guest.id
    assert order.correlation_id == correlation_id
    assert float(order.total_amount) == 24.0

    order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    assert len(order_items) == 1
    assert order_items[0].name == "Chicken Biryani"
    assert order_items[0].quantity == 2

    task = db.query(Task).filter(Task.tenant_id == "hotel-c").one()
    assert task.related_id == guest.id
