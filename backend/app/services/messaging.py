from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.integrations.base import SendResult
from app.integrations.email_providers import get_email_client
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
    """Reply webhook → store inbound message → update guest memory."""
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

    # Concierge Router (CONCIERGE.md §4/§4.1, roadmap step 7) — runs the
    # Escalation Filter first, then dispatches to exactly one of the four
    # agents. Its `AgentResponse` isn't sent to the guest yet: that
    # hand-off is the Conversation Manager's job (§5.5, not yet built —
    # the very next roadmap step), which owns history/dedup/tone/
    # throttling before anything goes out over WhatsApp. For now this
    # call's only *visible* effect is the same one the Escalation Filter
    # already had on its own before the Router existed: staff get
    # notified when a human is needed (whether that's the Escalation
    # Filter's own check, an agent's own should_escalate, or no agent
    # recognizing the message at all — see concierge_router.py). A
    # candidate reply an agent *could* give is logged, not sent, until
    # the Conversation Manager exists to own that hand-off.
    try:
        response = concierge_router.route(db, tenant_id=tenant_id, guest_id=guest.id, message_body=body)
        if response.handled and response.response:
            logger.info(
                "Concierge Router produced a candidate reply for guest %s via %s "
                "(not yet sent — awaiting Conversation Manager): %s",
                guest.id,
                response.metadata.get("agent"),
                response.response,
            )
    except ContextBuilderError:
        # A guest with a phone match but no resolvable Property (data
        # inconsistency) shouldn't block the inbound message itself from
        # being stored — log and move on rather than losing the message.
        logger.exception(
            "Concierge Router could not build context for guest %s", guest.id
        )

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
