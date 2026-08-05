"""Hotel trial signup tests."""

from app.core.security import hash_password
from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD
from app.db.session import get_db
from app.models.entities import Guest, Property, Tenant, User
from app.services.hotel_signup import ensure_trial_demo_data


def _db(client):
    return next(client.app.dependency_overrides[get_db]())


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

    roi = client.get("/api/analytics/roi?period_days=30", headers=headers)
    assert roi.status_code == 200
    assert "revenue_generated" in roi.json()

    approvals = client.get("/api/approvals?status=pending", headers=headers)
    assert approvals.status_code == 200
    assert len(approvals.json()) >= 1


def test_hotel_signup_always_seeds_even_when_flag_false(client):
    res = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Quiet Flag Hotel",
            "your_name": "Quinn",
            "email": "quinn.trial@example.com",
            "password": "TryRevisit1!",
            "include_sample_data": False,
        },
    )
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    guests = client.get("/api/guests", headers=headers)
    assert len(guests.json()) >= 5


def test_hotel_signup_duplicate_email(client):
    payload = {
        "hotel_name": "First Hotel",
        "your_name": "Ada",
        "email": "ada.trial@example.com",
        "password": "TryRevisit1!",
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
        },
    )
    login = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_trial_login_reseeds_empty_workspace(client):
    """Empty trial tenants get demo data restored on login."""
    email = "empty.trial@example.com"
    password = "TryRevisit1!"
    tenant_id = "empty-trial-inn-test1"

    db = _db(client)
    try:
        db.add(
            Tenant(id=tenant_id, name="Empty Trial Inn", plan="trial", is_active=True)
        )
        db.flush()
        db.add(
            User(
                tenant_id=tenant_id,
                email=email,
                name="Emptor",
                role="manager",
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        db.add(
            Property(
                tenant_id=tenant_id,
                name="Empty Trial Inn",
                type="hotel",
                city="Berlin",
                country="Germany",
                rooms=40,
            )
        )
        db.commit()
        assert db.query(Guest).filter(Guest.tenant_id == tenant_id).count() == 0
    finally:
        db.close()

    login = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    guests = client.get("/api/guests", headers=headers)
    assert guests.status_code == 200
    assert len(guests.json()) >= 5


def test_ensure_trial_demo_data_is_idempotent(client):
    res = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Idempotent Inn",
            "your_name": "Ida",
            "email": "ida.trial@example.com",
            "password": "TryRevisit1!",
        },
    )
    tenant_id = res.json()["tenant_id"]
    db = _db(client)
    try:
        assert ensure_trial_demo_data(db, tenant_id) is False
        count = db.query(Guest).filter(Guest.tenant_id == tenant_id).count()
        assert count >= 5
    finally:
        db.close()


def test_shared_demo_still_works(client):
    login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200


def test_login_matches_trial_when_email_also_on_demo(client):
    """Duplicate email across tenants must not block trial password re-login."""
    trial_password = "TrialPass9!"
    db = _db(client)
    try:
        db.add(
            Tenant(
                id="dup-email-trial",
                name="Azure Coast Resort",
                plan="trial",
                is_active=True,
            )
        )
        db.flush()
        db.add(
            User(
                tenant_id="dup-email-trial",
                email=DEMO_EMAIL,
                name="Deepanshu Khadikar",
                role="manager",
                password_hash=hash_password(trial_password),
                is_active=True,
            )
        )
        db.add(
            Property(
                tenant_id="dup-email-trial",
                name="Azure Coast Resort",
                type="hotel",
                city="Nice",
                country="France",
                rooms=48,
            )
        )
        db.commit()
    finally:
        db.close()

    trial_login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": trial_password},
    )
    assert trial_login.status_code == 200, trial_login.text
    assert trial_login.json()["user"]["tenant_id"] == "dup-email-trial"
    assert trial_login.json()["user"]["role"] == "manager"

    owner_login = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert owner_login.status_code == 200
    assert owner_login.json()["user"]["tenant_id"] == "demo-hotel"
    assert owner_login.json()["user"]["role"] == "admin"
