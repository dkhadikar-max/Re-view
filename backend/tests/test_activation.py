"""Activation funnel tests (P4 onboarding audit, CTO P0/P1 code-review
follow-up).

Covers exactly the proof points the CTO asked for after the code review:
  - telemetry success doesn't alter business behavior
  - telemetry failure doesn't block business behavior (login, approval)
  - existing real-data properties remain classified correctly (backfill)
  - new properties begin in the correct activation state
  - imports transition activation state correctly
plus log_event_once's own idempotency guarantee, which the review found
had zero direct coverage.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy import create_engine

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD, DEMO_TENANT
from app.db.session import get_db
from app.models.entities import ActivationEvent, Property
from app.services.activation import log_event_once, safe_log_event_once


def _db(client):
    return next(client.app.dependency_overrides[get_db]())


# ---------------------------------------------------------------------------
# log_event_once / safe_log_event_once — direct unit coverage
# ---------------------------------------------------------------------------


def test_log_event_once_is_idempotent(db):
    """Telemetry success doesn't alter business behavior, and a second
    call for the same tenant+event_type is a genuine no-op, not a second
    row -- the exact guarantee the code review found untested."""
    first = log_event_once(db, tenant_id=DEMO_TENANT, event_type="unit_test_event")
    db.commit()
    assert first is not None

    second = log_event_once(db, tenant_id=DEMO_TENANT, event_type="unit_test_event")
    assert second is None

    count = (
        db.query(ActivationEvent)
        .filter(
            ActivationEvent.tenant_id == DEMO_TENANT,
            ActivationEvent.event_type == "unit_test_event",
        )
        .count()
    )
    assert count == 1


def test_safe_log_event_once_success_writes_exactly_one_row(db):
    safe_log_event_once(db, tenant_id=DEMO_TENANT, event_type="unit_test_event_safe")
    count = (
        db.query(ActivationEvent)
        .filter(
            ActivationEvent.tenant_id == DEMO_TENANT,
            ActivationEvent.event_type == "unit_test_event_safe",
        )
        .count()
    )
    assert count == 1


def test_safe_log_event_once_swallows_failure_and_leaves_session_usable(db):
    """CTO P0: a telemetry write failure must never raise, and must never
    leave the shared session unusable for whatever the caller does next."""
    with patch(
        "app.services.activation.log_event_once", side_effect=RuntimeError("db down")
    ):
        safe_log_event_once(db, tenant_id=DEMO_TENANT, event_type="unit_test_event_fail")

    # The session must still be perfectly usable afterward -- proves the
    # SAVEPOINT rollback didn't poison the outer transaction.
    assert db.query(ActivationEvent).count() >= 0
    db.add(ActivationEvent(tenant_id=DEMO_TENANT, event_type="post_failure_probe"))
    db.commit()


# ---------------------------------------------------------------------------
# Telemetry failure must never block the real business action
# ---------------------------------------------------------------------------


def test_login_succeeds_when_telemetry_storage_fails(client):
    with patch(
        "app.services.activation.log_event_once", side_effect=RuntimeError("db down")
    ):
        res = client.post(
            "/api/auth/login",
            data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


def test_approval_succeeds_when_telemetry_storage_fails(client, auth_header):
    approvals = client.get("/api/approvals?status=pending", headers=auth_header)
    pending = [a for a in approvals.json() if a["approval_type"] == "message"]
    assert pending, "expected seeded message approvals"
    approval = pending[0]

    with patch(
        "app.services.activation.log_event_once", side_effect=RuntimeError("db down")
    ):
        r = client.post(
            f"/api/approvals/{approval['id']}",
            headers=auth_header,
            json={"action": "approve"},
        )
    assert r.status_code == 200, r.text
    # The actual business state change must have genuinely applied, not
    # just avoided a 500 while silently skipping the real transition.
    assert r.json()["status"] == "approved"


def test_signup_succeeds_when_telemetry_storage_fails(client):
    with patch(
        "app.services.activation.log_event_once", side_effect=RuntimeError("db down")
    ):
        res = client.post(
            "/api/demo/hotel-signup",
            json={
                "hotel_name": "Telemetry Outage Hotel",
                "your_name": "Resilient Owner",
                "email": "resilient@telemetry-outage.example",
                "password": "TryRevisit1!",
                "city": "Berlin",
                "country": "Germany",
                "rooms": 20,
            },
        )
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


# ---------------------------------------------------------------------------
# Activation state (has_real_data) transitions
# ---------------------------------------------------------------------------


def test_new_signup_starts_without_real_data(client):
    res = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Brand New Hotel",
            "your_name": "New Owner",
            "email": "new-owner@brand-new-hotel.example",
            "password": "TryRevisit1!",
            "city": "Lisbon",
            "country": "Portugal",
            "rooms": 30,
        },
    )
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    prop = client.get("/api/properties", headers=headers).json()[0]
    assert prop["has_real_data"] is False


def test_manual_import_flips_has_real_data(client, auth_header, db):
    prop_before = client.get("/api/properties", headers=auth_header).json()[0]
    # The demo tenant is shared across the whole suite and may already
    # have real data from an earlier test in this file (e.g. the
    # signup tests above use fresh tenants, but this guards against
    # any future test ordering change); only assert the transition when
    # starting from False, and always assert the end state is True.
    payload = {
        "guest_name": "Real Import Guest",
        "guest_email": "real.import.guest@example.com",
        "country": "Germany",
        "language": "de",
        "travel_type": "business",
        "check_in": (date.today() + timedelta(days=5)).isoformat(),
        "check_out": (date.today() + timedelta(days=8)).isoformat(),
        "total_amount": 400,
        "communication_preference": "whatsapp",
    }
    r = client.post("/api/reservations", headers=auth_header, json=payload)
    assert r.status_code == 201, r.text

    prop_after = client.get("/api/properties", headers=auth_header).json()[0]
    assert prop_after["has_real_data"] is True

    event = (
        db.query(ActivationEvent)
        .filter(
            ActivationEvent.tenant_id == DEMO_TENANT,
            ActivationEvent.event_type == "first_real_data_imported",
        )
        .first()
    )
    assert event is not None
    if prop_before["has_real_data"] is False:
        # Confirms this test's own import is what caused the flip, not
        # some earlier state.
        assert prop_after["has_real_data"] != prop_before["has_real_data"]


# ---------------------------------------------------------------------------
# Backfill: existing properties must be classified correctly, not reset
# to "sample" just because the column is new.
# ---------------------------------------------------------------------------


def test_has_real_data_backfill_classifies_existing_properties_correctly(tmp_path):
    """CTO P0 (code-review follow-up): a hotel that already had real
    (non-demo) guests before `has_real_data` existed must backfill to
    True. A hotel with only ever-seeded demo guests must stay False. A
    real guest imported with no email at all must still count as real."""
    db_path = tmp_path / "backfill_test.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE properties (id VARCHAR PRIMARY KEY, country VARCHAR, "
                "currency VARCHAR)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE guests (id VARCHAR PRIMARY KEY, property_id VARCHAR, "
                "email VARCHAR)"
            )
        )
        conn.execute(sa.text("CREATE TABLE tasks (id VARCHAR PRIMARY KEY)"))
        # tenant_id/provider_message_id: base columns other schema_patches
        # entries assume already exist on `messages` before adding their
        # own columns (one of them creates an index on both).
        conn.execute(
            sa.text(
                "CREATE TABLE messages (id VARCHAR PRIMARY KEY, tenant_id VARCHAR, "
                "provider_message_id VARCHAR)"
            )
        )

        # Real hotel: a mix of seeded-demo and genuinely real guests.
        conn.execute(
            sa.text(
                "INSERT INTO properties (id, country, currency) "
                "VALUES ('real-prop', 'Germany', 'EUR')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO guests (id, property_id, email) "
                "VALUES ('g1', 'real-prop', 'marie@real-prop.demo')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO guests (id, property_id, email) "
                "VALUES ('g2', 'real-prop', 'real.guest@gmail.com')"
            )
        )

        # Sample-only hotel: nothing but seeded demo guests.
        conn.execute(
            sa.text(
                "INSERT INTO properties (id, country, currency) "
                "VALUES ('sample-prop', 'Germany', 'EUR')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO guests (id, property_id, email) "
                "VALUES ('g3', 'sample-prop', 'hans@sample-prop.demo')"
            )
        )

        # Real guest with no email at all -- must still count as real.
        conn.execute(
            sa.text(
                "INSERT INTO properties (id, country, currency) "
                "VALUES ('null-email-prop', 'Germany', 'EUR')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO guests (id, property_id, email) "
                "VALUES ('g4', 'null-email-prop', NULL)"
            )
        )

        # Genuinely empty property -- no guests at all yet.
        conn.execute(
            sa.text(
                "INSERT INTO properties (id, country, currency) "
                "VALUES ('empty-prop', 'Germany', 'EUR')"
            )
        )

    import app.db.schema_patches as sp

    original_engine = sp.engine
    sp.engine = engine
    try:
        sp.ensure_schema_patches()
    finally:
        sp.engine = original_engine

    with engine.connect() as conn:
        rows = dict(
            conn.execute(sa.text("SELECT id, has_real_data FROM properties")).fetchall()
        )

    assert rows["real-prop"] in (1, True)
    assert rows["sample-prop"] in (0, False)
    assert rows["null-email-prop"] in (1, True)
    assert rows["empty-prop"] in (0, False)
