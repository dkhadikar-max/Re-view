"""Translation Layer — TRANSLATION_LAYER.md (7 frozen constraints).

Integration tests through `ingest_inbound_whatsapp`, the one production
call site wiring detect -> normalize -> existing Concierge pipeline ->
translate -> deliver into place (messaging.py). Uses a stub
TranslationClient (monkeypatched onto `messaging.translation_client`)
rather than the real OpenAI-backed one, so these tests are
deterministic and need no network access or API key — matching every
other agent test in this suite.

Each test below is named for the specific requirement from the CTO's
implementation-scope list it proves.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.integrations.translation import ENGLISH, TranslationError
from app.models.entities import (
    ActionEvent,
    Guest,
    Message,
    MessageStatus,
    Property,
    PropertyKnowledgeBase,
    Task,
    Tenant,
)
from app.services import messaging as messaging_module
from app.services.context_builder import ContextBuilder
from app.services.messaging import ingest_inbound_whatsapp


@pytest.fixture(autouse=True)
def _clear_context_cache():
    ContextBuilder.clear_cache()
    yield
    ContextBuilder.clear_cache()


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


def _make_tenant_with_guest(
    db, *, tenant_id, phone, language="en", whatsapp_configured=False
):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(
        tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany"
    )
    if whatsapp_configured:
        property_.whatsapp_phone_number_id = f"{tenant_id}-wa-number"
    db.add(property_)
    db.flush()
    guest = Guest(
        tenant_id=tenant_id,
        property_id=property_.id,
        name="Guest",
        phone=phone,
        language=language,
    )
    db.add(guest)
    db.flush()
    return guest, property_


class _StubTranslationClient:
    """Deterministic fake standing in for the real OpenAI-backed
    TranslationClient — a small fixed translation table, plus knobs to
    simulate provider failure independently on either leg."""

    def __init__(self):
        self.fail_detect = False
        # Direction-specific failure knobs — a real provider can fail on
        # one call and succeed on the next, and inbound normalization
        # (non-English -> English) vs outbound response translation
        # (English -> non-English) are two independent calls in
        # messaging.py. Conflating them would make it impossible to test
        # either failure mode in isolation.
        self.fail_translate_inbound = False
        self.fail_translate_outbound = False
        self.detect_calls: list[str] = []
        self.translate_calls: list[tuple[str, str, str]] = []
        # inbound text -> (detected_language, english_text)
        self._inbound = {
            "Hola, quiero pedir comida": ("es", "Hello, I want to order food"),
            "Tengo una emergencia médica": ("es", "I have a medical emergency"),
            "Hola, ¿a qué hora es el desayuno?": ("es", "What time is breakfast?"),
        }

    def detect_language(self, text: str) -> str:
        self.detect_calls.append(text)
        if self.fail_detect:
            raise TranslationError("stub: detection failed")
        known = self._inbound.get(text)
        return known[0] if known else ENGLISH

    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        self.translate_calls.append((text, source_language, target_language))
        if self.fail_translate_inbound and target_language == ENGLISH and source_language != ENGLISH:
            raise TranslationError("stub: inbound translation failed")
        if self.fail_translate_outbound and source_language == ENGLISH and target_language != ENGLISH:
            raise TranslationError("stub: outbound translation failed")
        if source_language == target_language:
            return text
        known = self._inbound.get(text)
        if known and target_language == ENGLISH:
            return known[1]
        # Outbound leg (English -> guest language) — a fixed, obviously-
        # tagged fake translation is all the assertions below need.
        return f"[{target_language}] {text}"


@pytest.fixture()
def stub_translation(monkeypatch):
    stub = _StubTranslationClient()
    monkeypatch.setattr(messaging_module, "translation_client", stub)
    return stub


# ---------------------------------------------------------------------------
# English no-op
# ---------------------------------------------------------------------------


def test_english_message_is_a_translation_noop(db_session, stub_translation):
    db = db_session
    guest, _ = _make_tenant_with_guest(db, tenant_id="hotel-en", phone="+15550001111")

    message = ingest_inbound_whatsapp(
        db, tenant_id="hotel-en", from_phone=guest.phone, body="What time is breakfast?"
    )

    assert message.detected_language == ENGLISH
    assert message.normalized_text is None  # never redundantly duplicated for English
    assert message.body == "What time is breakfast?"
    # No translate() call at all for an already-English round trip — no
    # KB is configured for this tenant, so there's no outbound response
    # either; only detect_language runs.
    assert stub_translation.translate_calls == []


# ---------------------------------------------------------------------------
# Supported non-English inbound + normalization + original-text preservation
# ---------------------------------------------------------------------------


def test_non_english_inbound_is_detected_normalized_and_original_preserved(
    db_session, stub_translation
):
    db = db_session
    guest, _ = _make_tenant_with_guest(db, tenant_id="hotel-es", phone="+15550002222")

    message = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-es",
        from_phone=guest.phone,
        body="Hola, quiero pedir comida",
    )

    assert message.detected_language == "es"
    assert message.normalized_text == "Hello, I want to order food"
    # Constraint 4: the original guest text is never overwritten.
    assert message.body == "Hola, quiero pedir comida"
    assert stub_translation.detect_calls == ["Hola, quiero pedir comida"]


# ---------------------------------------------------------------------------
# No Router/Agent semantic changes — the pipeline reacts to the English
# normalization exactly as it would to native English input.
# ---------------------------------------------------------------------------


def test_router_receives_normalized_english_not_original_language(
    db_session, stub_translation
):
    """A Spanish medical-emergency phrase must trip the same Escalation
    Filter hard-safety pattern a native-English guest saying the same
    thing already would — proving the Router/Escalation Filter never
    see anything but English, and their behavior is completely
    unchanged by the guest's actual language."""
    db = db_session
    guest, _ = _make_tenant_with_guest(db, tenant_id="hotel-med", phone="+15550003333")

    ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-med",
        from_phone=guest.phone,
        body="Tengo una emergencia médica",
    )

    tasks = db.query(Task).filter(Task.tenant_id == "hotel-med").all()
    assert len(tasks) == 1
    assert tasks[0].related_id == guest.id


# ---------------------------------------------------------------------------
# Outbound translation + delivery hookup
# ---------------------------------------------------------------------------


def test_outbound_response_translated_and_delivered_for_non_english_guest(
    db_session, stub_translation
):
    db = db_session
    guest, property_ = _make_tenant_with_guest(
        db, tenant_id="hotel-out", phone="+15550004444", whatsapp_configured=True
    )
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id, tenant_id="hotel-out", breakfast_hours="7-10am"
        )
    )
    db.flush()

    reply = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-out",
        from_phone=guest.phone,
        body="Hola, ¿a qué hora es el desayuno?",
    )
    assert reply is not None
    assert reply.detected_language == "es"
    assert reply.normalized_text == "What time is breakfast?"

    outbound_messages = (
        db.query(Message)
        .filter(Message.tenant_id == "hotel-out", Message.direction == "outbound")
        .all()
    )
    assert len(outbound_messages) == 1
    sent = outbound_messages[0]
    assert sent.language == "es"
    assert sent.body.startswith("[es] ")
    assert sent.status == MessageStatus.sent
    # The outbound leg actually ran (English -> Spanish), not a no-op.
    assert any(
        call[1] == ENGLISH and call[2] == "es" for call in stub_translation.translate_calls
    )


def test_outbound_response_is_english_noop_for_english_guest(db_session, stub_translation):
    db = db_session
    guest, property_ = _make_tenant_with_guest(
        db, tenant_id="hotel-out-en", phone="+15550004445", whatsapp_configured=True
    )
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id, tenant_id="hotel-out-en", breakfast_hours="7-10am"
        )
    )
    db.flush()

    ingest_inbound_whatsapp(
        db, tenant_id="hotel-out-en", from_phone=guest.phone, body="What time is breakfast?"
    )

    outbound_messages = (
        db.query(Message)
        .filter(Message.tenant_id == "hotel-out-en", Message.direction == "outbound")
        .all()
    )
    assert len(outbound_messages) == 1
    sent = outbound_messages[0]
    assert sent.language == ENGLISH
    assert sent.status == MessageStatus.sent
    assert "7" in sent.body
    # Fully English round trip — no translate() call at all.
    assert stub_translation.translate_calls == []


# ---------------------------------------------------------------------------
# Structured data untouched
# ---------------------------------------------------------------------------


def test_action_ledger_stays_canonical_regardless_of_guest_language(
    db_session, stub_translation
):
    db = db_session
    guest, property_ = _make_tenant_with_guest(db, tenant_id="hotel-ledger", phone="+15550006666")
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id, tenant_id="hotel-ledger", breakfast_hours="7-10am"
        )
    )
    db.flush()

    ingest_inbound_whatsapp(
        db, tenant_id="hotel-ledger", from_phone=guest.phone, body="What time is breakfast?"
    )

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-ledger").all()
    assert len(events) == 1
    event = events[0]
    # Structured/canonical fields — English, enum-shaped, never the
    # guest's raw text in any language.
    assert event.action_type == "FAQ_ANSWERED"
    assert event.intent == "information"
    assert "breakfast" in event.input_summary.lower()
    assert "hola" not in event.input_summary.lower()


def test_action_ledger_stays_canonical_for_non_english_guest(db_session, stub_translation):
    """Same assertion as above, but the guest actually wrote in Spanish
    — the Action Ledger content must be identical in shape regardless,
    proving translation never leaks into structured/logged fields."""
    db = db_session
    guest, property_ = _make_tenant_with_guest(db, tenant_id="hotel-ledger-es", phone="+15550006667")
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id, tenant_id="hotel-ledger-es", breakfast_hours="7-10am"
        )
    )
    db.flush()

    ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-ledger-es",
        from_phone=guest.phone,
        body="Hola, ¿a qué hora es el desayuno?",
    )

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-ledger-es").all()
    assert len(events) == 1
    event = events[0]
    assert event.action_type == "FAQ_ANSWERED"
    assert event.intent == "information"
    assert "breakfast" in event.input_summary.lower()
    assert "desayuno" not in event.input_summary.lower()
    assert "hola" not in event.input_summary.lower()


# ---------------------------------------------------------------------------
# Inbound failure — constraint 7
# ---------------------------------------------------------------------------


def test_inbound_translation_failure_skips_router_and_preserves_original_message(
    db_session, stub_translation
):
    db = db_session
    guest, _ = _make_tenant_with_guest(db, tenant_id="hotel-failin", phone="+15550007777")
    stub_translation.fail_detect = True

    message = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-failin",
        from_phone=guest.phone,
        body="Tengo una emergencia médica",
    )

    assert message is not None
    # The original message is safely stored — never lost.
    assert message.body == "Tengo una emergencia médica"
    assert message.detected_language is None
    assert message.normalized_text is None
    # The Router never ran: no ActionEvent, no staff Task — a translation
    # failure must never be silently reinterpreted as "nothing urgent."
    assert db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-failin").count() == 0
    assert db.query(Task).filter(Task.tenant_id == "hotel-failin").count() == 0


def test_inbound_normalization_failure_when_detection_succeeds_but_translate_fails(
    db_session, stub_translation
):
    """A distinct failure point from the test above: detection succeeds
    (we know the guest wrote Spanish) but the actual translate() call
    fails — must be treated identically (Router never invoked, original
    preserved), not partially handled just because detection worked."""
    db = db_session
    guest, _ = _make_tenant_with_guest(db, tenant_id="hotel-failin2", phone="+15550007778")
    stub_translation.fail_translate_inbound = True

    message = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-failin2",
        from_phone=guest.phone,
        body="Tengo una emergencia médica",
    )

    assert message is not None
    assert message.body == "Tengo una emergencia médica"
    # Detection itself succeeded and was recorded...
    assert message.detected_language == "es"
    # ...but normalization did not, so there's no fabricated English text.
    assert message.normalized_text is None
    assert db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-failin2").count() == 0
    assert db.query(Task).filter(Task.tenant_id == "hotel-failin2").count() == 0


# ---------------------------------------------------------------------------
# Outbound failure — constraint 7
# ---------------------------------------------------------------------------


def test_outbound_translation_failure_never_sends_untranslated_fallback(
    db_session, stub_translation
):
    db = db_session
    guest, property_ = _make_tenant_with_guest(
        db, tenant_id="hotel-failout", phone="+15550008888", whatsapp_configured=True
    )
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id, tenant_id="hotel-failout", breakfast_hours="7-10am"
        )
    )
    db.flush()

    stub_translation.fail_translate_outbound = True
    reply = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-failout",
        from_phone=guest.phone,
        body="Hola, ¿a qué hora es el desayuno?",
    )
    assert reply is not None
    # Inbound normalization used detect_language, not translate() — that
    # leg is unaffected by fail_translate, so the Router still ran and
    # the underlying decision is fully recorded (constraint 7: only
    # *delivery* is affected by an outbound translation failure).
    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-failout").all()
    assert len(events) == 1
    assert events[0].action_type == "FAQ_ANSWERED"

    outbound_messages = (
        db.query(Message)
        .filter(Message.tenant_id == "hotel-failout", Message.direction == "outbound")
        .all()
    )
    assert len(outbound_messages) == 1
    sent = outbound_messages[0]
    # Never silently sent the untranslated English text as a "fix".
    assert sent.status == MessageStatus.failed
    assert "7-10am" in sent.body


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_translation_state_is_scoped_per_tenant_and_message(db_session, stub_translation):
    db = db_session
    guest_a, _ = _make_tenant_with_guest(db, tenant_id="hotel-iso-a", phone="+15550009999")
    guest_b, _ = _make_tenant_with_guest(db, tenant_id="hotel-iso-b", phone="+15550001010")

    msg_a = ingest_inbound_whatsapp(
        db, tenant_id="hotel-iso-a", from_phone=guest_a.phone, body="Hola, quiero pedir comida"
    )
    msg_b = ingest_inbound_whatsapp(
        db, tenant_id="hotel-iso-b", from_phone=guest_b.phone, body="What time is breakfast?"
    )

    assert msg_a.detected_language == "es"
    assert msg_b.detected_language == ENGLISH
    # No shared/leaked state between tenants on the (process-wide) client.
    assert msg_a.tenant_id != msg_b.tenant_id
