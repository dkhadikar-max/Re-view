"""Password change and admin reset tests."""

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def test_change_password_and_login(client, auth_header):
    res = client.post(
        "/api/auth/change-password",
        headers=auth_header,
        json={
            "current_password": DEMO_PASSWORD,
            "new_password": "NewOwnerPass1!",
        },
    )
    assert res.status_code == 200, res.text
    assert "updated" in res.json()["message"].lower()

    bad = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert bad.status_code == 401

    good = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": "NewOwnerPass1!"},
    )
    assert good.status_code == 200


def test_admin_reset_password_for_trial(client):
    signup = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Reset Me Hotel",
            "your_name": "Riley Reset",
            "email": "riley.reset@example.com",
            "password": "OldPassword1!",
            "country": "Germany",
        },
    )
    assert signup.status_code == 200
    tenant_id = signup.json()["tenant_id"]

    owner = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert owner.status_code == 200
    headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}

    reset = client.post(
        f"/api/admin/clients/{tenant_id}/reset-password",
        headers=headers,
        json={},
    )
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["email"] == "riley.reset@example.com"
    assert body["temporary_password"]
    temp = body["temporary_password"]

    old = client.post(
        "/api/auth/login",
        data={"username": "riley.reset@example.com", "password": "OldPassword1!"},
    )
    assert old.status_code == 401

    neu = client.post(
        "/api/auth/login",
        data={"username": "riley.reset@example.com", "password": temp},
    )
    assert neu.status_code == 200


def test_trial_cannot_reset_others(client):
    signup = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "No Power Hotel",
            "your_name": "Nope",
            "email": "no.reset.power@example.com",
            "password": "TryRevisit1!",
        },
    )
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    assert (
        client.post(
            "/api/admin/clients/demo-hotel/reset-password",
            headers=headers,
            json={},
        ).status_code
        == 403
    )
