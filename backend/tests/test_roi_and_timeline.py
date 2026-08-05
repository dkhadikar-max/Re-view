"""ROI dashboard and revenue timeline tests."""

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def _auth(client):
    res = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_roi_metrics_endpoint(client):
    h = _auth(client)
    res = client.get("/api/analytics/roi", headers=h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "revenue_generated" in body
    assert "reviews_generated" in body
    assert "repeat_guests" in body
    assert "ai_hours_saved" in body
    assert "revenue_per_guest" in body
    assert "narrative" in body
    assert body["period_days"] == 30


def test_guest_revenue_timeline(client):
    h = _auth(client)
    guests = client.get("/api/guests", headers=h).json()
    marie = next(g for g in guests if g["name"] == "Marie Dupont")
    assert "lifetime_value" in marie
    assert marie["lifetime_value"] >= float(marie["lifetime_spend"])
    assert isinstance(marie.get("revenue_timeline"), list)
    assert len(marie["revenue_timeline"]) >= 1
    kinds = {e["kind"] for e in marie["revenue_timeline"]}
    assert "ltv" in kinds or "stay" in kinds
