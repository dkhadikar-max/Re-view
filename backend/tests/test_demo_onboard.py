"""Demo guest onboarding tests."""

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def _auth(client):
    res = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_demo_onboard_creates_rich_profile(client):
    res = client.post(
        "/api/demo/onboard",
        json={
            "name": "Client Demo Person",
            "email": "client.demo@example.com",
            "country": "Switzerland",
            "language": "en",
            "travel_type": "luxury",
            "purpose": "anniversary",
            "preferred_room": "Ocean Penthouse",
            "dietary_preferences": "vegetarian",
            "favorite_wine": "Pinot Noir",
            "remembers": ["Late checkout", "Sparkling water"],
            "company_or_hotel": "Alpine Hotels Group",
            "communication_preference": "whatsapp",
            "open_dashboard": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["guest"]["name"] == "Client Demo Person"
    assert body["guest"]["preferred_room"] == "Ocean Penthouse"
    assert body["guest"]["ai_summary"]
    assert body["guest"]["remembers"]
    assert any("Sparkling" in r or "sparkling" in r.lower() for r in body["guest"]["remembers"])
    assert body["guest"]["favorite_wine"] == "Pinot Noir"
    assert body["guest"]["ltv_score"] >= 85
    assert body["access_token"]
    assert body["dashboard_path"].startswith("/guests?guest=")

    # Session token works
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == DEMO_EMAIL

    # Appears in guest intelligence list
    h = _auth(client)
    guests = client.get("/api/guests", headers=h, params={"q": "Client Demo"}).json()
    assert any(g["name"] == "Client Demo Person" for g in guests)


def test_demo_onboard_upserts_by_email(client):
    payload = {
        "name": "Repeat Visitor",
        "email": "repeat.visitor@example.com",
        "travel_type": "business",
        "preferred_room": "Business King",
        "open_dashboard": False,
    }
    first = client.post("/api/demo/onboard", json=payload)
    assert first.status_code == 200
    gid = first.json()["guest"]["id"]
    assert first.json()["access_token"] is None

    second = client.post(
        "/api/demo/onboard",
        json={**payload, "name": "Repeat Visitor Updated", "preferred_room": "Suite 12"},
    )
    assert second.status_code == 200
    assert second.json()["guest"]["id"] == gid
    assert second.json()["guest"]["name"] == "Repeat Visitor Updated"
    assert second.json()["guest"]["preferred_room"] == "Suite 12"
