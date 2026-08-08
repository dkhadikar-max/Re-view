"""Knowledge Base Editor — the staff-facing CRUD surface over the
existing `PropertyKnowledgeBase` model. No new content architecture:
this file only tests the editor's own concerns — tenant isolation,
upsert semantics, partial updates, cache invalidation, audit
(field names only, wifi_password redacted), and the live preview
staying consistent with what FAQAgent would actually answer.
"""

from __future__ import annotations

import json

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.entities import AuditLog, PropertyKnowledgeBase, Tenant, User
from app.services.context_builder import ContextBuilder


def _db_session():
    override = app.dependency_overrides[get_db]
    return next(override())


def _get_property_id(client, auth_header) -> str:
    res = client.get("/api/properties", headers=auth_header)
    assert res.status_code == 200, res.text
    return res.json()[0]["id"]


def _kb_url(property_id: str) -> str:
    return f"/api/properties/{property_id}/knowledge-base"


def test_get_returns_empty_state_when_no_row_exists_yet(client, auth_header):
    property_id = _get_property_id(client, auth_header)

    res = client.get(_kb_url(property_id), headers=auth_header)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["wifi_password"] is None
    assert body["breakfast_hours"] is None
    assert body["preview"] == {}


def test_patch_creates_the_row_on_first_write(client, auth_header):
    property_id = _get_property_id(client, auth_header)

    res = client.patch(
        _kb_url(property_id),
        headers=auth_header,
        json={"wifi_password": "guest123", "pool_hours": "7am-9pm"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["wifi_password"] == "guest123"
    assert body["pool_hours"] == "7am-9pm"

    db = _db_session()
    try:
        rows = db.query(PropertyKnowledgeBase).filter(
            PropertyKnowledgeBase.property_id == property_id
        ).all()
        assert len(rows) == 1
    finally:
        db.close()


def test_patch_only_touches_fields_present_in_the_request(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    client.patch(
        _kb_url(property_id), headers=auth_header,
        json={"wifi_password": "guest123", "breakfast_hours": "7-10am"},
    )

    res = client.patch(
        _kb_url(property_id), headers=auth_header, json={"pool_hours": "6am-10pm"}
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pool_hours"] == "6am-10pm"
    # Untouched fields keep their previously-set values.
    assert body["wifi_password"] == "guest123"
    assert body["breakfast_hours"] == "7-10am"


def test_patch_with_explicit_null_clears_a_field(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    client.patch(_kb_url(property_id), headers=auth_header, json={"pet_policy": "No pets"})

    res = client.patch(_kb_url(property_id), headers=auth_header, json={"pet_policy": None})

    assert res.status_code == 200, res.text
    assert res.json()["pet_policy"] is None


def test_preview_reflects_faq_agent_wording_and_excludes_wifi_password(client, auth_header):
    property_id = _get_property_id(client, auth_header)

    res = client.patch(
        _kb_url(property_id),
        headers=auth_header,
        json={"wifi_password": "guest123", "checkout_time": "11am"},
    )

    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["checkout_time"] == "Check-out time is 11am."
    assert "wifi_password" not in preview


def test_audit_log_records_changed_field_names_not_values(client, auth_header):
    property_id = _get_property_id(client, auth_header)

    res = client.patch(
        _kb_url(property_id),
        headers=auth_header,
        json={"wifi_password": "super-secret-value", "spa_hours": "9am-8pm"},
    )
    assert res.status_code == 200, res.text

    db = _db_session()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "update_knowledge_base")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert entry is not None
        details = json.loads(entry.details)
        assert set(details["changed_fields"]) == {"wifi_password", "spa_hours"}
        # Never the actual values — especially not the credential.
        assert "super-secret-value" not in entry.details
        assert "9am-8pm" not in entry.details
    finally:
        db.close()


def test_patch_invalidates_the_context_cache(client, auth_header):
    ContextBuilder.clear_cache()
    property_id = _get_property_id(client, auth_header)
    guests = client.get("/api/guests", headers=auth_header).json()
    guest_id = guests[0]["id"]
    tenant_id = client.get("/api/auth/me", headers=auth_header).json()["tenant_id"]

    db = _db_session()
    try:
        # Prime the cache with the pre-edit state.
        before = ContextBuilder(db).build(tenant_id=tenant_id, guest_id=guest_id)
        assert before.knowledge_base is None or before.knowledge_base.gym_hours != "5am-11pm"
    finally:
        db.close()

    res = client.patch(_kb_url(property_id), headers=auth_header, json={"gym_hours": "5am-11pm"})
    assert res.status_code == 200, res.text

    db = _db_session()
    try:
        after = ContextBuilder(db).build(tenant_id=tenant_id, guest_id=guest_id)
        assert after.knowledge_base is not None
        assert after.knowledge_base.gym_hours == "5am-11pm"
    finally:
        db.close()
    ContextBuilder.clear_cache()


def test_cross_tenant_access_is_blocked(client, auth_header):
    property_id = _get_property_id(client, auth_header)
    client.patch(_kb_url(property_id), headers=auth_header, json={"wifi_password": "guest123"})

    db = _db_session()
    try:
        db.add(Tenant(id="other-hotel-kb", name="Other", plan="starter", is_active=True))
        db.flush()
        other_user = User(
            tenant_id="other-hotel-kb",
            email="other-kb@hotel.test",
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
        tenant_id="other-hotel-kb",
        email="other-kb@hotel.test",
        name="Other Manager",
        role="manager",
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    get_res = client.get(_kb_url(property_id), headers=other_headers)
    assert get_res.status_code == 404

    patch_res = client.patch(
        _kb_url(property_id), headers=other_headers, json={"wifi_password": "hijacked"}
    )
    assert patch_res.status_code == 404
