"""Hotel trial signup tests."""

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def test_hotel_signup_creates_tenant_and_logs_in(client):
    res = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Nordic Harbor Hotel",
            "your_name": "Erik Lind",
            "email": "erik@nordicharbor.example",
            "password": "TryRevisit1!",
            "city": "Stockholm",
            "country": "Sweden",
            "rooms": 62,
            "include_sample_data": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"]
    assert body["hotel_name"] == "Nordic Harbor Hotel"
    assert body["user"]["email"] == "erik@nordicharbor.example"
    assert body["user"]["role"] == "manager"
    assert body["tenant_id"].startswith("nordic-harbor-hotel-")

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "erik@nordicharbor.example"

    guests = client.get("/api/guests", headers=headers)
    assert guests.status_code == 200
    assert len(guests.json()) >= 3
    marie = next(g for g in guests.json() if g["name"] == "Marie Dupont")
    assert marie["ai_summary"]
    assert marie["remembers"]

    stats = client.get("/api/dashboard/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["total_guests"] >= 3


def test_hotel_signup_duplicate_email(client):
    payload = {
        "hotel_name": "First Hotel",
        "your_name": "Ada",
        "email": "ada.trial@example.com",
        "password": "TryRevisit1!",
        "include_sample_data": False,
    }
    assert client.post("/api/demo/hotel-signup", json=payload).status_code == 200
    again = client.post("/api/demo/hotel-signup", json={**payload, "hotel_name": "Second"})
    assert again.status_code == 409


def test_hotel_signup_can_login_again(client):
    email = "relogin@example.com"
    password = "TryRevisit1!"
    client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Relogin Inn",
            "your_name": "Riley",
            "email": email,
            "password": password,
            "include_sample_data": False,
        },
    )
    login = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_shared_demo_still_works(client):
    login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200
