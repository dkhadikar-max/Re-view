from app.core.security import create_access_token, hash_password
from app.main import app
from app.db.session import get_db
from app.models.entities import Tenant, User


def _db_session():
    override = app.dependency_overrides[get_db]
    return next(override())


def test_cross_tenant_idor_blocked(client, auth_header):
    db = _db_session()
    try:
        db.add(Tenant(id="other-hotel", name="Other", plan="starter", is_active=True))
        db.flush()
        other_user = User(
            tenant_id="other-hotel",
            email="other@hotel.test",
            name="Other Manager",
            role="manager",
            password_hash=hash_password("ChangeMe123!"),
            is_active=True,
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        other_id = other_user.id
    finally:
        db.close()

    guests = client.get("/api/guests", headers=auth_header).json()
    guest_id = guests[0]["id"]

    other_token = create_access_token(
        user_id=other_id,
        tenant_id="other-hotel",
        email="other@hotel.test",
        name="Other Manager",
        role="manager",
    )
    r = client.get(
        f"/api/guests/{guest_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert r.status_code == 404
    # Other tenant also sees empty guest list
    r2 = client.get(
        "/api/guests",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert r2.status_code == 200
    assert r2.json() == []
