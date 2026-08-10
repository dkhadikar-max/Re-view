from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.integrations.base import SendResult
from app.integrations.email_providers import get_email_client
from app.integrations.translation import ENGLISH, TranslationError, translation_client
from app.integrations.whatsapp import whatsapp_client
from app.models.entities import Guest, Message, MessageChannel, MessageStatus, Property
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilderError
from app.services.state_machine import MESSAGE_TRANSITIONS, transition

logger = logging.getLogger(__name__)


def _property_for_message(db: Session, message: Message) -> Property | None:
    return db.query(Property).filter(Property.tenant_id == message.tenant_id).first()


def _send_via_whatsapp(db: Session, message: Message, to: str) -> SendResult:
    """Resolves which of ReVisit's WABA-hosted numbers this tenant's
    property owns and sends through it — never a shared/global number
    (CONCIERGE.md §3; outbound routing follows the same rule inbound
    already does). Raises if the property has no number configured yet,
    which `deliver_message`'s existing exception handling already turns
    into a logged, failed message rather than a silent wrong-number send.
    """
    property_ = _property_for_message(db, message)
    if not property_ or not property_.whatsapp_phone_number_id:
        raise ValueError(
            f"Tenant {message.tenant_id}'s property has no configured "
            "WhatsApp phone_number_id — cannot send without knowing which "
            "number this hotel's guests were told to message"
        )
    return whatsapp_client.send(
        phone_number_id=property_.whatsapp_phone_number_id,
        to=to,
        body=message.body,
        subject=message.subject,
    )


def _recipient_for(db: Session, message: Message) -> str:
    guest = db.get(Guest, message.guest_id)
    if not guest:
        raise ValueError("Guest missing for message")
    if message.channel == MessageChannel.whatsapp:
        if not guest.phone:
            raise ValueError("Guest has no phone for WhatsApp")
        return guest.phone
    if message.channel == MessageChannel.email:
        if not guest.email:
            raise ValueError("Guest has no email")
        return guest.email
    # SMS fallback to phone
    if not guest.phone:
        raise ValueError("Guest has no phone for SMS")
    return guest.phone


def deliver_message(db: Session, message: Message) -> Message:
    if message.status not in (MessageStatus.queued,):
        raise ValueError(f"Cannot deliver message in status {message.status}")

    to = _recipient_for(db, message)
    try:
        if message.channel == MessageChannel.whatsapp:
            result = _send_via_whatsapp(db, message, to)
        elif message.channel == MessageChannel.email:
            result = get_email_client().send(
                to=to, body=message.body, subject=message.subject
            )
        else:
            # SMS: reuse WhatsApp mock path until Twilio is added — same
            # per-property phone_number_id requirement applies.
            result = _send_via_whatsapp(db, message, to)

        transition(message.status, MessageStatus.sent, MESSAGE_TRANSITIONS, "message")
        message.status = MessageStatus.sent
        message.provider_message_id = result.provider_message_id
        message.sent_at = datetime.utcnow()
        db.flush()
        logger.info(
            "Delivered message %s via %s → %s",
            message.id,
            result.provider,
            result.provider_message_id,
        )
    except Exception:
        transition(message.status, MessageStatus.failed, MESSAGE_TRANSITIONS, "message")
        message.status = MessageStatus.failed
        db.flush()
        raise
    return message


def apply_provider_status(
    db: Session, provider_message_id: str, status: str
) -> Message | None:
    message = (
        db.query(Message)
        .filter(Message.provider_message_id == provider_message_id)
        .first()
    )
    if not message:
        return None
    status = status.lower()
    if status == "delivered" and message.status == MessageStatus.sent:
        transition(message.status, MessageStatus.delivered, MESSAGE_TRANSITIONS, "message")
        message.status = MessageStatus.delivered
    elif status == "read" and message.status in (
        MessageStatus.sent,
        MessageStatus.delivered,
    ):
        if message.status == MessageStatus.sent:
            transition(message.status, MessageStatus.delivered, MESSAGE_TRANSITIONS, "message")
            message.status = MessageStatus.delivered
        # read tracked via notes on guest for V1
        guest = db.get(Guest, message.guest_id)
        if guest:
            note = f"WhatsApp read receipt for message {message.id}"
            guest.notes = f"{guest.notes}\n{note}" if guest.notes else note
    elif status == "failed":
        transition(message.status, MessageStatus.failed, MESSAGE_TRANSITIONS, "message")
        message.status = MessageStatus.failed
    db.flush()
    return message


def ingest_inbound_whatsapp(
    db: Session,
    *,
    tenant_id: str,
    from_phone: str,
    body: str,
    provider_message_id: str | None = None,
    contact_name: str | None = None,
) -> Message | None:
    """Reply webhook → store inbound message → update guest memory.

    PILOT_READINESS.md §1 — webhook idempotency. Meta retries webhook
    delivery on timeout or a non-2xx response; without a dedup check, a
    retried webhook re-runs this entire function a second time (a
    second `Message`, a second `ActionEvent`, potentially a second
    `Order`/`Task`, a second guest-memory note). Dedup key is the
    `(tenant_id, provider_message_id)` pair, not `provider_message_id`
    alone — ReVisit's platform-level WABA (`CONCIERGE.md` §3) means a
    dedup bug must never be able to cross a tenant boundary even in
    theory, even though Meta's own IDs are already globally unique.
    Conditional on `provider_message_id` being present: some inbound
    event shapes may lack it, and two such events must never be treated
    as duplicates of each other.
    """
    if provider_message_id:
        existing = (
            db.query(Message)
            .filter(
                Message.tenant_id == tenant_id,
                Message.provider_message_id == provider_message_id,
            )
            .first()
        )
        if existing:
            logger.info(
                "Duplicate inbound webhook for tenant=%s provider_message_id=%s "
                "— returning existing message %s, not re-processing",
                tenant_id,
                provider_message_id,
                existing.id,
            )
            return existing

    phone_digits = "".join(ch for ch in from_phone if ch.isdigit())
    guests = db.query(Guest).filter(Guest.tenant_id == tenant_id).all()
    guest = None
    for g in guests:
        if g.phone and "".join(ch for ch in g.phone if ch.isdigit()).endswith(
            phone_digits[-10:]
        ):
            guest = g
            break
    if not guest:
        logger.warning("Inbound WhatsApp from unknown phone %s", from_phone)
        return None

    message = Message(
        tenant_id=tenant_id,
        guest_id=guest.id,
        channel=MessageChannel.whatsapp,
        direction="inbound",
        language=guest.language or "en",
        subject="WhatsApp reply",
        body=body,
        status=MessageStatus.delivered,
        message_type="inbound_reply",
        provider_message_id=provider_message_id,
        sent_at=datetime.utcnow(),
    )
    db.add(message)
    # Guest memory enrichment
    memory = f"Inbound WhatsApp ({datetime.utcnow().isoformat()}): {body[:280]}"
    guest.notes = f"{guest.notes}\n{memory}" if guest.notes else memory
    if contact_name and not guest.name:
        guest.name = contact_name
    # Simple preference signal
    lower = body.lower()
    if any(w in lower for w in ("yes", "ok", "please", "book", "ja", "oui")):
        guest.upsell_acceptance = min(1.0, float(guest.upsell_acceptance or 0) + 0.1)
    db.flush()

    # Translation Layer (TRANSLATION_LAYER.md) — inbound normalization,
    # strictly before the Concierge pipeline ever runs. `message.body`
    # above is never touched (constraint 4); this only ever produces a
    # *new* value the Router is handed instead of `body`.
    try:
        detected_language = translation_client.detect_language(body)
        message.detected_language = detected_language
        if detected_language == ENGLISH:
            normalized_body = body
        else:
            normalized_body = translation_client.translate(
                body, source_language=detected_language, target_language=ENGLISH
            )
            message.normalized_text = normalized_body
        db.flush()
    except TranslationError:
        # Constraint 7: a failure here must never reach the Router with a
        # fabricated English interpretation. The guest's original message
        # is already safely stored above (untouched) — only the pipeline
        # run for *this turn* is skipped, same "log and move on" shape
        # this function already uses for ContextBuilderError below.
        logger.exception(
            "Inbound translation failed for guest %s — Concierge Router not "
            "invoked for this message (TRANSLATION_LAYER.md constraint 7)",
            guest.id,
        )
        return message

    # Concierge Router (CONCIERGE.md §4/§4.1, roadmap step 7) — runs the
    # Escalation Filter first, then dispatches to exactly one of the four
    # agents, or hands off to the Conversation Manager if a PendingAction
    # is already open. Always receives `normalized_body` (English), never
    # the guest's original-language `body` — TRANSLATION_LAYER.md §0: the
    # pipeline stays entirely language-agnostic and unaware translation
    # exists at all.
    try:
        response = concierge_router.route(
            db, tenant_id=tenant_id, guest_id=guest.id, message_body=normalized_body
        )
    except ContextBuilderError:
        # A guest with a phone match but no resolvable Property (data
        # inconsistency) shouldn't block the inbound message itself from
        # being stored — log and move on rather than losing the message.
        logger.exception(
            "Concierge Router could not build context for guest %s", guest.id
        )
        return message

    # Outbound delivery hookup (TRANSLATION_LAYER.md, CTO decision:
    # "minimal and independently testable"). This is a mechanical check
    # on `response.response` alone — it does not inspect `handled` or
    # `should_escalate` to decide whether to send, matching every existing
    # path through `concierge_router.route()` that already decides for
    # itself whether there is guest-facing text at all (an escalation-
    # only turn already returns `response=None`).
    if response.response:
        # `message.detected_language` is always set by this point — any
        # inbound translation failure already returned above before the
        # Router ever ran, so there's no "detection failed but we got
        # this far" case to fall back from. `guest.language` (the
        # guest's separately-declared preference) is deliberately NOT
        # consulted here — TRANSLATION_LAYER.md §2 constraint 3 keeps
        # the two concepts distinct, and per-property translation policy
        # (which might one day prefer `guest.language`) is explicitly
        # deferred (CTO decision, v1 scope).
        target_language = message.detected_language or ENGLISH
        outbound = Message(
            tenant_id=tenant_id,
            guest_id=guest.id,
            channel=MessageChannel.whatsapp,
            direction="outbound",
            language=target_language,
            subject="Concierge reply",
            body=response.response,
            status=MessageStatus.queued,
            message_type="concierge_reply",
        )
        db.add(outbound)
        db.flush()
        if target_language != ENGLISH:
            try:
                outbound.body = translation_client.translate(
                    response.response, source_language=ENGLISH, target_language=target_language
                )
                db.flush()
            except TranslationError:
                # Constraint 7: never send an untranslated English
                # fallback dressed up as a fix, and never roll back the
                # decision the pipeline already made and logged above —
                # only delivery to the guest is affected. The existing
                # failed-message state is the same operational signal any
                # other delivery failure already produces.
                logger.exception(
                    "Outbound translation failed for guest %s — leaving the "
                    "message undelivered rather than sending an "
                    "untranslated fallback (TRANSLATION_LAYER.md "
                    "constraint 7)",
                    guest.id,
                )
                transition(outbound.status, MessageStatus.failed, MESSAGE_TRANSITIONS, "message")
                outbound.status = MessageStatus.failed
                db.flush()
                return message
        try:
            deliver_message(db, outbound)
        except Exception:  # noqa: BLE001 — deliver_message already logs/transitions internally
            logger.exception("Failed delivering concierge reply to guest %s", guest.id)

    return message


def process_due_messages(db: Session, limit: int = 50) -> int:
    now = datetime.utcnow()
    due = (
        db.query(Message)
        .filter(
            Message.status == MessageStatus.queued,
            Message.scheduled_at.isnot(None),
            Message.scheduled_at <= now,
        )
        .order_by(Message.scheduled_at.asc())
        .limit(limit)
        .all()
    )
    immediate = (
        db.query(Message)
        .filter(Message.status == MessageStatus.queued, Message.scheduled_at.is_(None))
        .limit(max(0, limit - len(due)))
        .all()
    )
    count = 0
    for message in due + immediate:
        try:
            deliver_message(db, message)
            count += 1
        except Exception:  # noqa: BLE001
            logger.exception("Failed delivering message %s", message.id)
    return count
