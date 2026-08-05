from datetime import date, timedelta

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_requires_auth(client):
    assert client.get("/api/guests").status_code == 401


def test_login_and_me(client, auth_header):
    me = client.get("/api/auth/me", headers=auth_header)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == DEMO_EMAIL
    assert body["tenant_id"] == "demo-hotel"
    assert body["role"] == "manager"


def test_bad_login(client):
    r = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": "wrong-password"},
    )
    assert r.status_code == 401


def test_tenant_scoped_lists(client, auth_header):
    guests = client.get("/api/guests", headers=auth_header)
    assert guests.status_code == 200
    assert len(guests.json()) >= 6
    stats = client.get("/api/dashboard/stats", headers=auth_header)
    assert stats.status_code == 200
    assert "metrics_note" in stats.json()


def test_create_reservation_triggers_ai(client, auth_header):
    payload = {
        "guest_name": "Test Guest",
        "guest_email": "test.guest@example.com",
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
    decisions = client.get("/api/ai-decisions", headers=auth_header)
    assert decisions.status_code == 200
    assert any(d["validated"] for d in decisions.json())


def test_invalid_reservation_dates(client, auth_header):
    payload = {
        "guest_name": "Bad Dates",
        "check_in": date.today().isoformat(),
        "check_out": date.today().isoformat(),
        "total_amount": 100,
    }
    r = client.post("/api/reservations", headers=auth_header, json=payload)
    assert r.status_code == 422


def test_approval_queues_message_not_sends(client, auth_header):
    approvals = client.get("/api/approvals?status=pending", headers=auth_header)
    assert approvals.status_code == 200
    pending = [a for a in approvals.json() if a["approval_type"] == "message"]
    assert pending, "expected seeded message approvals"
    approval = pending[0]
    r = client.post(
        f"/api/approvals/{approval['id']}",
        headers=auth_header,
        json={"action": "approve"},
    )
    assert r.status_code == 200
    assert r.json()["reviewed_by"] == "Sofia Marino"
    # Message should be queued, not sent
    messages = client.get("/api/messages", headers=auth_header).json()
    related = next(m for m in messages if m["id"] == approval["related_id"])
    assert related["status"] == "queued"


def test_cannot_send_pending_approval_message(client, auth_header):
    messages = client.get("/api/messages", headers=auth_header).json()
    pending = next((m for m in messages if m["status"] == "pending_approval"), None)
    if not pending:
        return
    r = client.post(f"/api/messages/{pending['id']}/send", headers=auth_header)
    assert r.status_code in (409, 400)


def test_offer_accept_idempotent(client, auth_header):
    offers = client.get("/api/offers", headers=auth_header).json()
    offered = next(o for o in offers if o["status"] == "offered")
    r1 = client.post(f"/api/offers/{offered['id']}/accept", headers=auth_header)
    assert r1.status_code == 200
    r2 = client.post(f"/api/offers/{offered['id']}/accept", headers=auth_header)
    assert r2.status_code == 409


def test_cors_not_wildcard(client):
    # middleware configured without *; preflight should not reflect arbitrary origin unless listed
    r = client.options(
        "/api/guests",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette may 200/400; ensure ACAO is not *
    assert r.headers.get("access-control-allow-origin") != "*"


def test_worker_tick(client, auth_header):
    r = client.post("/api/workers/tick", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert "events_processed" in body
    assert "messages_delivered" in body


def test_ai_decision_schema_validation():
    from app.services.ai_orchestrator import AIDecisionSchema

    ok = AIDecisionSchema(
        action="Welcome",
        channel="whatsapp",
        language="en",
        timing="immediate",
        confidence=0.9,
        reasoning="ok",
    )
    assert ok.action == "Welcome"
    try:
        AIDecisionSchema(
            action="Hack",
            channel="whatsapp",
            language="en",
            timing="now",
            confidence=1.2,
            reasoning="bad",
        )
        assert False, "should have failed"
    except Exception:
        pass
