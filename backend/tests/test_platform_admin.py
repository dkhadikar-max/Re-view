"""Platform owner admin panel tests."""

import os

from app.core.config import Settings
from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def _owner_headers(client):
    login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["user"]["is_platform_admin"] is True
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_owner_me_is_platform_admin(client):
    headers = _owner_headers(client)
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["is_platform_admin"] is True
    assert me.json()["email"] == DEMO_EMAIL


def test_empty_owner_email_env_still_grants_admin():
    """Blank OWNER_EMAIL must not disable /admin (matches seed fallback)."""
    previous = os.environ.get("OWNER_EMAIL")
    os.environ["OWNER_EMAIL"] = ""
    try:
        settings = Settings()
        assert settings.owner_email == "dkhadikar@gmail.com"
        from app.core.security import CurrentUser, is_platform_owner
        import app.core.security as security

        user = CurrentUser(
            id="1",
            tenant_id="demo-hotel",
            email="dkhadikar@gmail.com",
            name="Deepanshu",
            role="admin",
        )
        original = security.settings
        security.settings = settings
        try:
            assert is_platform_owner(user) is True
        finally:
            security.settings = original
    finally:
        if previous is None:
            os.environ.pop("OWNER_EMAIL", None)
        else:
            os.environ["OWNER_EMAIL"] = previous


def test_admin_clients_and_analytics(client):
    # Create a trial hotel first
    signup = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Admin View Inn",
            "your_name": "Casey Client",
            "email": "casey.adminview@example.com",
            "password": "TryRevisit1!",
            "city": "Mumbai",
            "country": "India",
            "rooms": 55,
        },
    )
    assert signup.status_code == 200, signup.text

    headers = _owner_headers(client)
    clients = client.get("/api/admin/clients", headers=headers)
    assert clients.status_code == 200
    rows = clients.json()
    assert any(c["hotel_name"] == "Admin View Inn" for c in rows)
    trial = next(c for c in rows if c["hotel_name"] == "Admin View Inn")
    assert trial["plan"] == "trial"
    assert trial["manager_email"] == "casey.adminview@example.com"
    assert trial["currency"] == "INR"
    assert trial["country"] == "India"
    assert trial["guest_count"] >= 1

    analytics = client.get("/api/admin/analytics", headers=headers)
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["total_hotels"] >= 2
    assert body["trial_hotels"] >= 1
    assert any(s["hotel_name"] == "Admin View Inn" for s in body["recent_signups"])
    assert any(p["plan"] == "trial" for p in body["by_plan"])
    assert any(c["country"] == "India" for c in body["by_country"])


def test_trial_manager_cannot_access_admin(client):
    signup = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Blocked Access Hotel",
            "your_name": "No Admin",
            "email": "no.admin@example.com",
            "password": "TryRevisit1!",
            "country": "Germany",
        },
    )
    assert signup.status_code == 200
    token = signup.json()["access_token"]
    assert signup.json()["user"]["is_platform_admin"] is False
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/admin/clients", headers=headers).status_code == 403
    assert client.get("/api/admin/analytics", headers=headers).status_code == 403
