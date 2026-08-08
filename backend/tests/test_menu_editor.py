"""Menu editor endpoint — MENU_ORDERING.md §3.3. HTTP-level tests for
`GET /menu-items` and `PATCH /menu-items/{id}`, mirroring
test_knowledge_base_editor.py's established pattern for a staff-facing
editor: tenant isolation, partial updates, and audit trail. Extraction/
classification/import logic itself is covered at the service level in
test_menu_importer.py.
"""

from __future__ import annotations

import json

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.entities import AuditLog, MenuItem, Property, Tenant, User


def _db_session():
    override = app.dependency_overrides[get_db]
    return next(override())


def _get_property_id(client, auth_header) -> str:
    res = client.get("/api/properties", headers=auth_header)
    assert res.status_code == 200, res.text
    return res.json()[0]["id"]


def _seed_menu_item(tenant_id: str, property_id: str) -> str:
    db = _db_session()
    try:
        item = MenuItem(
            tenant_id=tenant_id, property_id=property_id, menu_name="Dinner",
            name="Grilled Salmon", price=24.0, currency="EUR",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id
    finally:
        db.close()


def test_get_menu_items_lists_only_this_tenants_items(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    _seed_menu_item(tenant_id="demo-hotel", property_id=property_id)

    res = client.get("/api/menu-items", headers=auth_header)

    assert res.status_code == 200, res.text
    names = [item["name"] for item in res.json()]
    assert "Grilled Salmon" in names


def test_patch_updates_only_fields_present(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    item_id = _seed_menu_item(tenant_id="demo-hotel", property_id=property_id)

    res = client.patch(
        f"/api/menu-items/{item_id}", headers=auth_header, json={"price": 26.0}
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["price"] == 26.0
    assert body["name"] == "Grilled Salmon"  # untouched


def test_patch_can_mark_unavailable(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    item_id = _seed_menu_item(tenant_id="demo-hotel", property_id=property_id)

    res = client.patch(
        f"/api/menu-items/{item_id}", headers=auth_header, json={"available": False}
    )

    assert res.status_code == 200, res.text
    assert res.json()["available"] is False


def test_patch_records_audit_entry_with_changed_field_names(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    item_id = _seed_menu_item(tenant_id="demo-hotel", property_id=property_id)

    res = client.patch(
        f"/api/menu-items/{item_id}", headers=auth_header,
        json={"price": 26.0, "category": "Main Course"},
    )
    assert res.status_code == 200, res.text

    db = _db_session()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "update_menu_item")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert entry is not None
        details = json.loads(entry.details)
        assert set(details["changed_fields"]) == {"price", "category"}
    finally:
        db.close()


def test_menu_item_id_is_preserved_across_the_editor_endpoint(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    item_id = _seed_menu_item(tenant_id="demo-hotel", property_id=property_id)

    res = client.patch(
        f"/api/menu-items/{item_id}", headers=auth_header, json={"price": 30.0}
    )

    assert res.status_code == 200, res.text
    assert res.json()["id"] == item_id


def test_cross_tenant_access_is_blocked(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    item_id = _seed_menu_item(tenant_id="demo-hotel", property_id=property_id)

    db = _db_session()
    try:
        db.add(Tenant(id="other-hotel-menu", name="Other", plan="starter", is_active=True))
        db.flush()
        other_user = User(
            tenant_id="other-hotel-menu",
            email="other-menu@hotel.test",
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

    other_token = create_access_token(
        user_id=other_id,
        tenant_id="other-hotel-menu",
        email="other-menu@hotel.test",
        name="Other Manager",
        role="manager",
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    get_res = client.get("/api/menu-items", headers=other_headers)
    assert get_res.status_code == 200
    assert get_res.json() == []

    patch_res = client.patch(
        f"/api/menu-items/{item_id}", headers=other_headers, json={"price": 1.0}
    )
    assert patch_res.status_code == 404
