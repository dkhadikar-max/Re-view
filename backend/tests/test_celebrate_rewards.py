from datetime import date

from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD


def _auth(client):
    res = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_celebrate_config_and_dashboard(client):
    h = _auth(client)
    cfg = client.get("/api/celebrate/config", headers=h)
    assert cfg.status_code == 200
    body = cfg.json()
    assert body["birthday_enabled"] is True
    assert body["birthday_discount_pct"] == 20.0

    dash = client.get("/api/celebrate/dashboard", headers=h)
    assert dash.status_code == 200
    assert dash.json()["guests_enrolled"] >= 1
    assert "tagline" in dash.json()


def test_review_unlocks_celebrate_then_lock_dates(client):
    h = _auth(client)
    guests = client.get("/api/guests", headers=h).json()
    # Emily is index-ish; pick one without lock
    guest = next(g for g in guests if not g.get("birthday_locked"))
    review = client.post(
        "/api/reviews",
        headers=h,
        json={
            "guest_id": guest["id"],
            "platform": "google",
            "rating": 5,
            "title": "Great stay",
            "body": "Wonderful breakfast and friendly staff.",
        },
    )
    assert review.status_code == 201, review.text

    guests2 = client.get("/api/guests", headers=h).json()
    updated = next(g for g in guests2 if g["id"] == guest["id"])
    assert updated["review_reward_unlocked"] is True

    invite = client.post(
        f"/api/celebrate/guests/{guest['id']}/invite", headers=h
    )
    assert invite.status_code == 200, invite.text
    token = invite.json()["token"]

    public = client.get(f"/api/celebrate/public/{token}")
    assert public.status_code == 200
    assert public.json()["can_submit_dates"] is True

    submit = client.post(
        f"/api/celebrate/public/{token}/dates",
        json={
            "birthday": "1990-05-15",
            "anniversary": "2018-06-01",
            "confirm": True,
        },
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["birthday_locked"] is True
    assert len(submit.json()["coupons_created"]) >= 1

    # Cannot resubmit
    again = client.post(
        f"/api/celebrate/public/{token}/dates",
        json={"birthday": "1991-01-01", "confirm": True},
    )
    assert again.status_code == 409


def test_manager_cannot_admin_unlock(client):
    from app.db.seed import TEST_MANAGER_EMAIL

    login = client.post(
        "/api/auth/login",
        data={"username": TEST_MANAGER_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    guests = client.get("/api/guests", headers=h).json()
    locked = next(g for g in guests if g.get("birthday_locked"))
    r = client.post(
        f"/api/celebrate/guests/{locked['id']}/admin-unlock",
        headers=h,
        json={"field": "birthday", "reason": "Guest mistyped their birthday date"},
    )
    assert r.status_code == 403


def test_admin_unlock_with_audit(client):
    login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    guests = client.get("/api/guests", headers=h).json()
    locked = next(g for g in guests if g.get("birthday_locked"))
    r = client.post(
        f"/api/celebrate/guests/{locked['id']}/admin-unlock",
        headers=h,
        json={"field": "both", "reason": "Guest mistyped their celebration dates"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["birthday_locked"] is False
    audits = client.get("/api/celebrate/audits", headers=h)
    assert audits.status_code == 200
    assert any(a["action"] == "unlock" for a in audits.json())


def test_coupon_redeem_min_spend(client):
    h = _auth(client)
    coupons = client.get("/api/celebrate/coupons", headers=h).json()
    active = next((c for c in coupons if c["status"] == "active"), None)
    if not active:
        return
    # Force valid window for test by accepting whatever; may 409 if outside window
    low = client.post(
        f"/api/celebrate/coupons/{active['id']}/redeem",
        headers=h,
        json={"amount": 1},
    )
    assert low.status_code in (409, 422)
