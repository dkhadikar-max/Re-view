"""Staff Task E2E evidence — PILOT_READINESS.md §5.

`complete_task` (`POST /api/tasks/{id}/complete`) used to update
`Task.status` and stop there — no `TASK_COMPLETED` `ActionEvent`, so
the evidence chain for "did the hotel actually do the thing" had no
last step. These tests cover the fix end-to-end through the real API
boundary (auth, tenant scoping, HTTP status codes), against Tasks
created via the same service-level paths every other agent/manager
test in this suite already uses to produce them:

- offer/order acceptance -> `conversation_manager._accept()`
- a low-confidence memory update -> `memory_manager._hold()`
- a hard-safety message -> `concierge_router.route()` -> `escalate_to_staff()`

In every case `Task.correlation_id` (PILOT_READINESS.md §5, set at
Task-creation time) must be the same id the resulting `TASK_COMPLETED`
event carries, and no other `ActionEvent` in the chain may be touched.
"""

from __future__ import annotations

import json

import pytest

from app.db.seed import DEMO_TENANT
from app.models.entities import (
    ActionEvent,
    ActionEventStatus,
    ActorType,
    Guest,
    Property,
    Task,
    TaskStatus,
    Tenant,
)
from app.services.action_logger import action_logger
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import conversation_manager
from app.services.memory_manager import memory_manager


@pytest.fixture(autouse=True)
def _clear_context_cache():
    ContextBuilder.clear_cache()
    yield
    ContextBuilder.clear_cache()


def _make_guest(db, *, tenant_id=DEMO_TENANT, phone):
    property_ = db.query(Property).filter(Property.tenant_id == tenant_id).first()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Task Test Guest", phone=phone)
    db.add(guest)
    db.commit()
    return guest


def _task_completed_events(db, correlation_id):
    return (
        db.query(ActionEvent)
        .filter(ActionEvent.correlation_id == correlation_id, ActionEvent.action_type == "TASK_COMPLETED")
        .all()
    )


# ---------------------------------------------------------------------------
# Origin 1: offer/order acceptance (conversation_manager._accept)
# ---------------------------------------------------------------------------


def test_complete_task_offer_accepted_origin_propagates_correlation(client, auth_header, db):
    guest = _make_guest(db, phone="+15551234000")
    event = action_logger.log_action(
        db,
        tenant_id=DEMO_TENANT,
        guest_id=guest.id,
        intent="service_request",
        agent="revenue",
        action_type="OFFER_PROPOSED",
        actor=ActorType.ai,
        input_summary="Guest requested late checkout.",
        decision="RevenueAgent proposed paid late checkout.",
        status=ActionEventStatus.proposed,
    )
    db.commit()
    pending = conversation_manager.register_proposal(db, event=event)
    db.commit()
    context = ContextBuilder(db).build(tenant_id=DEMO_TENANT, guest_id=guest.id)
    conversation_manager.resolve(db, context, pending, "Yes please, go ahead")
    db.commit()

    task = db.query(Task).filter(Task.tenant_id == DEMO_TENANT, Task.related_id == guest.id).one()
    assert task.correlation_id == event.correlation_id

    # Capture the pre-existing chain's state so we can prove completion
    # never mutates it (check 7).
    pre_events = {
        e.action_type: (e.status, e.decision)
        for e in db.query(ActionEvent).filter(ActionEvent.correlation_id == event.correlation_id).all()
    }
    assert set(pre_events) == {"OFFER_PROPOSED", "OFFER_ACCEPTED", "TASK_CREATED"}

    res = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert res.status_code == 200, res.text
    assert res.json() == {"ok": True}

    db.expire_all()
    events = db.query(ActionEvent).filter(ActionEvent.correlation_id == event.correlation_id).all()
    by_type = {e.action_type: e for e in events}
    assert set(by_type) == {"OFFER_PROPOSED", "OFFER_ACCEPTED", "TASK_CREATED", "TASK_COMPLETED"}
    assert by_type["TASK_COMPLETED"].actor == ActorType.staff
    assert by_type["TASK_COMPLETED"].correlation_id == event.correlation_id
    assert by_type["TASK_COMPLETED"].status == ActionEventStatus.completed

    # The three original events are byte-for-byte unchanged (check 7).
    for action_type, (status, decision) in pre_events.items():
        assert by_type[action_type].status == status
        assert by_type[action_type].decision == decision

    refreshed_task = db.query(Task).filter(Task.id == task.id).one()
    assert refreshed_task.status == TaskStatus.done


# ---------------------------------------------------------------------------
# Origin 2: low-confidence memory update (memory_manager._hold)
# ---------------------------------------------------------------------------


def test_complete_task_memory_hold_origin_propagates_correlation(client, auth_header, db):
    guest = _make_guest(db, phone="+15551234001")
    event = action_logger.log_action(
        db,
        tenant_id=DEMO_TENANT,
        guest_id=guest.id,
        intent="memory",
        agent="guest_memory",
        action_type="MEMORY_PROPOSED",
        actor=ActorType.ai,
        input_summary="Guest shared a preference.",
        decision="GuestMemoryAgent proposed updating a field.",
        status=ActionEventStatus.proposed,
    )
    db.commit()
    memory_manager.apply_or_hold(
        db,
        event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.75}],
    )
    db.commit()

    task = db.query(Task).filter(Task.tenant_id == DEMO_TENANT, Task.related_id == guest.id).one()
    assert task.correlation_id == event.correlation_id

    res = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert res.status_code == 200, res.text

    db.expire_all()
    events = _task_completed_events(db, event.correlation_id)
    assert len(events) == 1
    assert events[0].actor == ActorType.staff
    assert events[0].correlation_id == event.correlation_id

    # MEMORY_HELD is untouched.
    held = (
        db.query(ActionEvent)
        .filter(ActionEvent.correlation_id == event.correlation_id, ActionEvent.action_type == "MEMORY_HELD")
        .one()
    )
    assert held.status == ActionEventStatus.escalated


# ---------------------------------------------------------------------------
# Origin 3: hard-safety escalation (concierge_router -> escalate_to_staff)
# ---------------------------------------------------------------------------


def test_complete_task_escalation_origin_propagates_correlation(client, auth_header, db):
    guest = _make_guest(db, phone="+15551234002")

    concierge_router.route(
        db,
        tenant_id=DEMO_TENANT,
        guest_id=guest.id,
        message_body="I need an ambulance, medical emergency",
    )
    db.commit()

    task = db.query(Task).filter(Task.tenant_id == DEMO_TENANT, Task.related_id == guest.id).one()
    escalated = (
        db.query(ActionEvent)
        .filter(
            ActionEvent.tenant_id == DEMO_TENANT,
            ActionEvent.guest_id == guest.id,
            ActionEvent.action_type == "ESCALATED",
        )
        .one()
    )
    # PILOT_READINESS.md §5 — the ESCALATED event and the Task it
    # produced now share one id, generated before either existed.
    assert task.correlation_id == escalated.correlation_id

    res = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert res.status_code == 200, res.text

    db.expire_all()
    events = _task_completed_events(db, escalated.correlation_id)
    assert len(events) == 1
    assert events[0].actor == ActorType.staff

    refreshed_escalated = db.query(ActionEvent).filter(ActionEvent.id == escalated.id).one()
    assert refreshed_escalated.status == ActionEventStatus.escalated  # untouched


# ---------------------------------------------------------------------------
# Auth / tenant scoping / not-found
# ---------------------------------------------------------------------------


def test_complete_task_requires_auth(client, db):
    guest = _make_guest(db, phone="+15551234003")
    task = Task(
        tenant_id=DEMO_TENANT,
        title="Unauthenticated test",
        status=TaskStatus.open,
        related_type="guest",
        related_id=guest.id,
    )
    db.add(task)
    db.commit()

    res = client.post(f"/api/tasks/{task.id}/complete")
    assert res.status_code == 401


def test_complete_task_cross_tenant_returns_404(client, auth_header, db):
    db.add(Tenant(id="other-hotel", name="Other Hotel"))
    property_ = Property(tenant_id="other-hotel", name="Other Hotel Prop", city="Rome", country="Italy")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id="other-hotel", property_id=property_.id, name="Other Guest", phone="+15551234004")
    db.add(guest)
    db.flush()
    task = Task(
        tenant_id="other-hotel",
        title="Belongs to a different tenant",
        status=TaskStatus.open,
        related_type="guest",
        related_id=guest.id,
    )
    db.add(task)
    db.commit()

    # auth_header authenticates as DEMO_TENANT ("demo-hotel") staff —
    # must not be able to complete another tenant's Task.
    res = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert res.status_code == 404


def test_complete_task_nonexistent_returns_404(client, auth_header):
    res = client.post("/api/tasks/no-such-task-id/complete", headers=auth_header)
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Idempotency — check 6
# ---------------------------------------------------------------------------


def test_complete_task_already_completed_returns_409_and_no_duplicate_event(client, auth_header, db):
    guest = _make_guest(db, phone="+15551234005")
    task = Task(
        tenant_id=DEMO_TENANT,
        title="Idempotency test",
        status=TaskStatus.open,
        related_type="guest",
        related_id=guest.id,
        correlation_id="corr-already-done",
    )
    db.add(task)
    db.commit()

    first = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert first.status_code == 200

    second = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert second.status_code == 409

    db.expire_all()
    events = _task_completed_events(db, "corr-already-done")
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Tasks with no ActionEvent origin (reviews, onboarding) — no guest_id
# available, so no TASK_COMPLETED is emitted, but completion still works.
# ---------------------------------------------------------------------------


def test_complete_task_without_guest_origin_completes_without_action_event(client, auth_header, db):
    task = Task(
        tenant_id=DEMO_TENANT,
        title="Negative review follow-up (no guest-chain origin)",
        status=TaskStatus.open,
        related_type="review",
        related_id="some-review-id",
    )
    db.add(task)
    db.commit()

    res = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert res.status_code == 200, res.text

    db.expire_all()
    refreshed = db.query(Task).filter(Task.id == task.id).one()
    assert refreshed.status == TaskStatus.done

    events = db.query(ActionEvent).filter(
        ActionEvent.tenant_id == DEMO_TENANT, ActionEvent.action_type == "TASK_COMPLETED"
    ).all()
    assert not any(json.loads(e.event_metadata).get("task_id") == task.id for e in events)


# ---------------------------------------------------------------------------
# A guest-origin Task with no correlation_id (legacy row) still gets a
# TASK_COMPLETED event — just with a fresh, standalone correlation_id
# rather than a fabricated link to a chain it was never part of.
# ---------------------------------------------------------------------------


def test_complete_task_with_no_correlation_id_still_logs_task_completed(client, auth_header, db):
    guest = _make_guest(db, phone="+15551234006")
    task = Task(
        tenant_id=DEMO_TENANT,
        title="Legacy task, no correlation_id",
        status=TaskStatus.open,
        related_type="guest",
        related_id=guest.id,
        correlation_id=None,
    )
    db.add(task)
    db.commit()

    res = client.post(f"/api/tasks/{task.id}/complete", headers=auth_header)
    assert res.status_code == 200, res.text

    db.expire_all()
    event = (
        db.query(ActionEvent)
        .filter(
            ActionEvent.tenant_id == DEMO_TENANT,
            ActionEvent.action_type == "TASK_COMPLETED",
            ActionEvent.guest_id == guest.id,
        )
        .one()
    )
    assert event.correlation_id is not None
    assert event.actor == ActorType.staff
