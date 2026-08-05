"""Guest Intelligence API tests."""

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def _auth(client):
    res = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_guest_list_returns_intelligence(client):
    h = _auth(client)
    res = client.get("/api/guests", headers=h)
    assert res.status_code == 200
    guests = res.json()
    assert len(guests) >= 1
    marie = next(g for g in guests if g["name"] == "Marie Dupont")
    assert marie["loyalty_label"]
    assert marie["health"] in {"loyal", "neutral", "at_risk"}
    assert "return_probability" in marie
    assert marie["ai_summary"]
    assert isinstance(marie["tags"], list)
    assert isinstance(marie["remembers"], list)
    assert len(marie["remembers"]) >= 1
    assert marie["preferred_room"] == "Sea View Suite"
    assert marie["next_best_action"] is not None


def test_guest_opportunities(client):
    h = _auth(client)
    res = client.get("/api/guests/opportunities", headers=h)
    assert res.status_code == 200
    opps = res.json()
    assert isinstance(opps, list)
    assert len(opps) >= 1
    assert "guest_name" in opps[0]
    assert "action_label" in opps[0]


def test_guest_intelligent_filters(client):
    h = _auth(client)
    res = client.get(
        "/api/guests",
        params={"min_spend": 1000, "min_stays": 2},
        headers=h,
    )
    assert res.status_code == 200
    guests = res.json()
    assert all(float(g["lifetime_spend"]) >= 1000 for g in guests)
    assert all(g["stay_count"] >= 2 for g in guests)

    res_q = client.get(
        "/api/guests",
        params={"q": "vegetarian"},
        headers=h,
    )
    assert res_q.status_code == 200
    names = [g["name"] for g in res_q.json()]
    assert "Marie Dupont" in names


def test_no_cloudbeds_placeholder_names_in_mock(client):
    from app.integrations.cloudbeds import cloudbeds_client

    rows, _ = cloudbeds_client._mock_fetch("0")
    for row in rows:
        assert "Cloudbeds Guest" not in row.guest.name
        assert "Guest 1" not in row.guest.name
