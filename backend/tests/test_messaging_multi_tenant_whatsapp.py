"""Outbound WhatsApp must use each tenant's own phone_number_id, never a
shared/global one — the outbound half of CONCIERGE.md §3's multi-tenant
routing (the inbound half is covered in test_integrations_v1.py).

Four checks, matching the pre-merge checklist this PR was built against:
1. Guest messages Hotel A -> reply comes from Hotel A's number.
2. Guest messages Hotel B -> reply comes from Hotel B's number.
3. Property has no configured phone_number_id -> fails gracefully, not a
   silent wrong-number send.
4. A single-property deployment (the common case today) keeps working
   once its number is configured — no special-casing required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.integrations.base import SendResult
from app.models.entities import (
    Guest,
    Message,
    MessageChannel,
    MessageStatus,
    Property,
    Tenant,
)
from app.services.messaging import deliver_message


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


def _make_tenant_property_guest(db, *, tenant_id, phone_number_id, guest_phone):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(
        tenant_id=tenant_id,
        name=f"{tenant_id} Hotel",
        city="Berlin",
        country="Germany",
        whatsapp_phone_number_id=phone_number_id,
    )
    db.add(property_)
    db.flush()
    guest = Guest(
        tenant_id=tenant_id, property_id=property_.id, name="Guest", phone=guest_phone
    )
    db.add(guest)
    db.flush()
    return property_, guest


def _queued_whatsapp_message(db, *, tenant_id, guest_id, body="Hello"):
    message = Message(
        tenant_id=tenant_id,
        guest_id=guest_id,
        channel=MessageChannel.whatsapp,
        status=MessageStatus.queued,
        body=body,
    )
    db.add(message)
    db.flush()
    return message


def test_outbound_whatsapp_uses_each_propertys_own_number(db_session):
    db = db_session
    _, guest_a = _make_tenant_property_guest(
        db, tenant_id="hotel-a", phone_number_id="PHONE_A", guest_phone="+15550001111"
    )
    _, guest_b = _make_tenant_property_guest(
        db, tenant_id="hotel-b", phone_number_id="PHONE_B", guest_phone="+15550002222"
    )
    message_a = _queued_whatsapp_message(db, tenant_id="hotel-a", guest_id=guest_a.id)
    message_b = _queued_whatsapp_message(db, tenant_id="hotel-b", guest_id=guest_b.id)

    calls: list[str] = []

    def fake_send(*, phone_number_id, to, body, subject=None):
        calls.append(phone_number_id)
        return SendResult(
            provider="whatsapp", provider_message_id="wamid.test", status="sent"
        )

    with patch("app.services.messaging.whatsapp_client.send", side_effect=fake_send):
        deliver_message(db, message_a)
        deliver_message(db, message_b)

    assert calls == ["PHONE_A", "PHONE_B"]
    assert message_a.status == MessageStatus.sent
    assert message_b.status == MessageStatus.sent


def test_outbound_whatsapp_fails_gracefully_without_configured_number(db_session):
    db = db_session
    _, guest = _make_tenant_property_guest(
        db, tenant_id="hotel-c", phone_number_id=None, guest_phone="+15550003333"
    )
    message = _queued_whatsapp_message(db, tenant_id="hotel-c", guest_id=guest.id)

    with pytest.raises(ValueError):
        deliver_message(db, message)
    assert message.status == MessageStatus.failed


def test_outbound_whatsapp_single_property_deployment_still_works(db_session):
    db = db_session
    _, guest = _make_tenant_property_guest(
        db, tenant_id="solo-hotel", phone_number_id="PHONE_SOLO", guest_phone="+15550004444"
    )
    message = _queued_whatsapp_message(db, tenant_id="solo-hotel", guest_id=guest.id)

    def fake_send(*, phone_number_id, to, body, subject=None):
        assert phone_number_id == "PHONE_SOLO"
        return SendResult(
            provider="whatsapp", provider_message_id="wamid.solo", status="sent"
        )

    with patch("app.services.messaging.whatsapp_client.send", side_effect=fake_send):
        deliver_message(db, message)

    assert message.status == MessageStatus.sent


def test_whatsapp_client_send_rejects_missing_phone_number_id():
    """Defense in depth at the client level itself, independent of
    messaging.py's own check — no caller can accidentally send without
    specifying which number, even if a future call site forgets the
    property lookup."""
    from app.integrations.whatsapp import WhatsAppCloudClient

    client = WhatsAppCloudClient()
    with pytest.raises(ValueError):
        client.send(phone_number_id=None, to="+15550000000", body="hi")
