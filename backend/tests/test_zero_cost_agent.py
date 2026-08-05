"""Zero-cost agent — routine guest ops without LLM spend."""

from datetime import date, timedelta
from types import SimpleNamespace

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD
from app.services.zero_cost_agent import AGENT_NAME, choose_routine_action


def _auth(client):
    login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_choose_routine_actions():
    guest = SimpleNamespace(
        name="Ada Lovelace",
        language="en",
        communication_preference="whatsapp",
        travel_type="business",
        purpose=None,
        ltv_score=70,
        children=0,
    )
    near = SimpleNamespace(
        check_in=date.today() + timedelta(days=1),
        check_out=date.today() + timedelta(days=3),
    )
    far = SimpleNamespace(
        check_in=date.today() + timedelta(days=10),
        check_out=date.today() + timedelta(days=12),
    )
    past = SimpleNamespace(
        check_in=date.today() - timedelta(days=5),
        check_out=date.today() - timedelta(days=2),
    )
    assert choose_routine_action(guest, near) == "Welcome"
    assert choose_routine_action(guest, far) == "Upsell"
    assert choose_routine_action(guest, far, {"intent": "reminder"}) == "BookingReminder"
    assert choose_routine_action(guest, past) == "ReviewRequest"
    assert (
        choose_routine_action(guest, past, {"force_action": "FeedbackRequest"})
        == "FeedbackRequest"
    )


def test_decide_endpoint_uses_zero_cost_agent(client):
    headers = _auth(client)
    status = client.get("/api/integrations/status", headers=headers)
    assert status.status_code == 200
    providers = {i["provider"]: i for i in status.json()["integrations"]}
    assert "Zero-Cost Agent" in providers
    assert providers["Zero-Cost Agent"]["configured"] is True

    rows = client.get("/api/reservations", headers=headers)
    assert rows.status_code == 200 and rows.json()
    rid = rows.json()[0]["id"]
    res = client.post(f"/api/reservations/{rid}/decide", headers=headers)
    assert res.status_code == 200, res.text

    decisions = client.get("/api/ai-decisions", headers=headers)
    assert decisions.status_code == 200
    assert decisions.json()
    assert decisions.json()[0]["model_name"] == AGENT_NAME
    raw = decisions.json()[0].get("raw_output") or ""
    assert "zero-cost-agent" in raw or decisions.json()[0]["model_name"] == AGENT_NAME
