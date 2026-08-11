"""Monitoring and alerting — PILOT_READINESS.md §4.

`pilot_health()` is a single tenant-scoped aggregate — deliberately not
a full observability platform (see the doc's explicit non-goal). These
tests cover each of the five signals independently, plus the tenant
scoping and window-bounding that make the numbers trustworthy, and the
`GET /api/pilot-health` endpoint's auth/shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    Property,
    Task,
    TaskStatus,
    Tenant,
)
from app.services.messaging import MAX_OUTBOUND_RETRIES
from app.services.pilot_health import pilot_health


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


def _make_guest(db, *, tenant_id, phone="+15550000000"):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(
        tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany"
    )
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest", phone=phone)
    db.add(guest)
    db.flush()
    return guest


def _message(db, *, tenant_id, guest_id, **overrides):
    defaults = dict(
        tenant_id=tenant_id,
        guest_id=guest_id,
        channel=MessageChannel.whatsapp,
        direction="inbound",
        body="hello",
        status=MessageStatus.delivered,
    )
    defaults.update(overrides)
    message = Message(**defaults)
    db.add(message)
    db.flush()
    return message


def test_inbound_processing_failures_counted(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-health-1")
    _message(db, tenant_id="hotel-health-1", guest_id=guest.id, processing_failed=True,
              failure_reason="translation_error")
    _message(db, tenant_id="hotel-health-1", guest_id=guest.id, processing_failed=True,
              failure_reason="context_builder_error")
    _message(db, tenant_id="hotel-health-1", guest_id=guest.id)  # unaffected message

    result = pilot_health(db, tenant_id="hotel-health-1")

    assert result.inbound_processing_failures == 2


def test_translation_failures_are_a_distinct_subset(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-health-2")
    _message(db, tenant_id="hotel-health-2", guest_id=guest.id, processing_failed=True,
              failure_reason="translation_error")
    _message(db, tenant_id="hotel-health-2", guest_id=guest.id, direction="outbound",
              status=MessageStatus.failed, failure_reason="outbound_translation_error")
    # A generic processing failure — NOT a translation failure.
    _message(db, tenant_id="hotel-health-2", guest_id=guest.id, processing_failed=True,
              failure_reason="context_builder_error")

    result = pilot_health(db, tenant_id="hotel-health-2")

    assert result.inbound_processing_failures == 2
    assert result.translation_failures == 2


def test_outbound_delivery_failed_split_active_vs_exhausted(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-health-3")
    _message(db, tenant_id="hotel-health-3", guest_id=guest.id, direction="outbound",
              status=MessageStatus.failed, retry_count=1)
    _message(db, tenant_id="hotel-health-3", guest_id=guest.id, direction="outbound",
              status=MessageStatus.failed, retry_count=MAX_OUTBOUND_RETRIES)
    # A successfully delivered message must never be counted either way.
    _message(db, tenant_id="hotel-health-3", guest_id=guest.id, direction="outbound",
              status=MessageStatus.sent)

    result = pilot_health(db, tenant_id="hotel-health-3")

    assert result.outbound_delivery_failed_active == 1
    assert result.outbound_delivery_exhausted == 1


def test_duplicate_webhooks_detected(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-health-4")
    _message(db, tenant_id="hotel-health-4", guest_id=guest.id, duplicate_webhook_count=3)
    _message(db, tenant_id="hotel-health-4", guest_id=guest.id, duplicate_webhook_count=0)

    result = pilot_health(db, tenant_id="hotel-health-4")

    assert result.duplicate_webhooks_detected == 1


def test_stale_open_tasks_older_than_window(db_session):
    db = db_session
    db.add(Tenant(id="hotel-health-5", name="hotel-health-5"))
    db.flush()
    stale = Task(
        tenant_id="hotel-health-5", title="Stale task", status=TaskStatus.open,
        created_at=datetime.utcnow() - timedelta(hours=48),
    )
    fresh = Task(
        tenant_id="hotel-health-5", title="Fresh task", status=TaskStatus.open,
        created_at=datetime.utcnow() - timedelta(hours=1),
    )
    done = Task(
        tenant_id="hotel-health-5", title="Done task", status=TaskStatus.done,
        created_at=datetime.utcnow() - timedelta(hours=48),
    )
    db.add_all([stale, fresh, done])
    db.flush()

    result = pilot_health(db, tenant_id="hotel-health-5", hours=24)

    assert result.stale_open_tasks == 1


def test_window_bounds_out_old_messages(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-health-6")
    old = _message(db, tenant_id="hotel-health-6", guest_id=guest.id, processing_failed=True,
                    failure_reason="translation_error")
    old.created_at = datetime.utcnow() - timedelta(hours=100)
    db.flush()

    result = pilot_health(db, tenant_id="hotel-health-6", hours=24)

    assert result.inbound_processing_failures == 0
    assert result.window_hours == 24


def test_tenant_scoping(db_session):
    db = db_session
    guest_a = _make_guest(db, tenant_id="hotel-health-a")
    guest_b = _make_guest(db, tenant_id="hotel-health-b")
    _message(db, tenant_id="hotel-health-a", guest_id=guest_a.id, processing_failed=True,
              failure_reason="translation_error")
    _message(db, tenant_id="hotel-health-b", guest_id=guest_b.id, processing_failed=True,
              failure_reason="translation_error")

    result_a = pilot_health(db, tenant_id="hotel-health-a")

    assert result_a.inbound_processing_failures == 1


def test_pilot_health_endpoint_requires_auth(client):
    res = client.get("/api/pilot-health")
    assert res.status_code == 401


def test_pilot_health_endpoint_returns_zeroed_summary_for_clean_tenant(client, auth_header):
    res = client.get("/api/pilot-health", headers=auth_header)
    assert res.status_code == 200
    body = res.json()
    assert body["window_hours"] == 24
    for key in (
        "inbound_processing_failures",
        "translation_failures",
        "outbound_delivery_failed_active",
        "outbound_delivery_exhausted",
        "duplicate_webhooks_detected",
        "stale_open_tasks",
    ):
        assert key in body


def test_pilot_health_endpoint_accepts_hours_query_param(client, auth_header):
    res = client.get("/api/pilot-health?hours=1", headers=auth_header)
    assert res.status_code == 200
    assert res.json()["window_hours"] == 1


def test_pilot_health_endpoint_rejects_out_of_range_hours(client, auth_header):
    res = client.get("/api/pilot-health?hours=0", headers=auth_header)
    assert res.status_code == 422
    res = client.get("/api/pilot-health?hours=1000", headers=auth_header)
    assert res.status_code == 422
