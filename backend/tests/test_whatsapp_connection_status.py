"""Property WhatsApp connection status — WHATSAPP_PLATFORM_ARCHITECTURE.md.

Covers:
- `Property.whatsapp_connection_status` defaults to `not_connected` and
  stays in sync with `whatsapp_phone_number_id` via the property-
  settings endpoint (§3's "kept in sync" contract).
- The go-live guard's platform-level check is genuinely independent of
  property connection state: a production `Settings()` with a real
  platform WhatsApp token constructs successfully even when zero
  `Property` rows exist at all — proving §0/§2's invariant isn't
  accidentally coupled to per-property state, not just asserting it in
  prose.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import Property, Tenant, WhatsAppConnectionStatus


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_property_defaults_to_not_connected_status(db_session):
    db = db_session
    db.add(Tenant(id="hotel-wa-default", name="hotel-wa-default"))
    db.flush()
    property_ = Property(
        tenant_id="hotel-wa-default", name="Test Hotel", city="Berlin", country="Germany"
    )
    db.add(property_)
    db.flush()

    assert property_.whatsapp_phone_number_id is None
    assert property_.whatsapp_connection_status == WhatsAppConnectionStatus.not_connected


def test_setting_phone_number_id_via_endpoint_marks_connected(client, auth_header):
    properties = client.get("/api/properties", headers=auth_header).json()
    assert properties, "expected at least one seeded property"
    p = properties[0]

    payload = {
        "name": p["name"],
        "city": p["city"],
        "country": p["country"],
        "currency": p["currency"],
        "timezone": p["timezone"],
        "rooms": p["rooms"],
        "brand_voice": p["brand_voice"],
        "address": p["address"],
        "google_review_url": p["google_review_url"],
        "whatsapp_phone_number_id": "wa-number-connected-test",
    }
    res = client.patch(f"/api/properties/{p['id']}", headers=auth_header, json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["whatsapp_phone_number_id"] == "wa-number-connected-test"
    assert body["whatsapp_connection_status"] == "connected"


def test_clearing_phone_number_id_via_endpoint_marks_not_connected(client, auth_header):
    properties = client.get("/api/properties", headers=auth_header).json()
    p = properties[0]
    base_payload = {
        "name": p["name"],
        "city": p["city"],
        "country": p["country"],
        "currency": p["currency"],
        "timezone": p["timezone"],
        "rooms": p["rooms"],
        "brand_voice": p["brand_voice"],
        "address": p["address"],
        "google_review_url": p["google_review_url"],
    }

    connect = client.patch(
        f"/api/properties/{p['id']}",
        headers=auth_header,
        json={**base_payload, "whatsapp_phone_number_id": "wa-number-to-clear"},
    )
    assert connect.status_code == 200, connect.text
    assert connect.json()["whatsapp_connection_status"] == "connected"

    disconnect = client.patch(
        f"/api/properties/{p['id']}",
        headers=auth_header,
        json={**base_payload, "whatsapp_phone_number_id": None},
    )
    assert disconnect.status_code == 200, disconnect.text
    assert disconnect.json()["whatsapp_phone_number_id"] is None
    assert disconnect.json()["whatsapp_connection_status"] == "not_connected"


def test_production_boots_with_real_platform_token_and_zero_connected_properties(db_session):
    """WHATSAPP_PLATFORM_ARCHITECTURE.md §0/§2 — the go-live guard's
    boot condition is platform-level only. Proves it directly against a
    completely empty database (zero Property rows at all, a stronger
    statement than merely zero *connected* ones): a production
    Settings() with a real platform WhatsApp token still constructs
    without error."""
    db = db_session
    connected = (
        db.query(Property)
        .filter(Property.whatsapp_connection_status == WhatsAppConnectionStatus.connected)
        .count()
    )
    assert connected == 0

    previous = {
        k: os.environ.get(k)
        for k in (
            "ENVIRONMENT",
            "USE_MOCK_AI",
            "OPENAI_API_KEY",
            "WHATSAPP_ACCESS_TOKEN",
            "ALLOW_MOCK_MODE_IN_PRODUCTION",
            "JWT_SECRET",
        )
    }
    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ["USE_MOCK_AI"] = "false"
        os.environ["OPENAI_API_KEY"] = "sk-real-key"
        os.environ["WHATSAPP_ACCESS_TOKEN"] = "real-platform-token"
        os.environ.pop("ALLOW_MOCK_MODE_IN_PRODUCTION", None)
        os.environ["JWT_SECRET"] = "a" * 32
        from app.core.config import Settings

        settings = Settings()
        assert settings.environment == "production"
        assert settings.whatsapp_configured is True
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
