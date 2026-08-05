from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import Message, MessageChannel, MessageStatus
from app.services.state_machine import MESSAGE_TRANSITIONS, transition

logger = logging.getLogger(__name__)


class MessagingProvider:
    """Delivery adapter. Real providers plug in here."""

    name = "mock"

    def send(self, message: Message) -> str:
        provider_id = f"{self.name}_{uuid.uuid4().hex[:12]}"
        logger.info(
            "Delivered message %s via %s channel=%s provider_id=%s",
            message.id,
            self.name,
            message.channel,
            provider_id,
        )
        return provider_id


PROVIDERS = {
    MessageChannel.whatsapp: MessagingProvider(),
    MessageChannel.email: MessagingProvider(),
    MessageChannel.sms: MessagingProvider(),
}


def deliver_message(db: Session, message: Message) -> Message:
    if message.status not in (MessageStatus.queued,):
        raise ValueError(f"Cannot deliver message in status {message.status}")
    provider = PROVIDERS.get(message.channel, MessagingProvider())
    try:
        provider_id = provider.send(message)
        transition(message.status, MessageStatus.sent, MESSAGE_TRANSITIONS, "message")
        message.status = MessageStatus.sent
        message.provider_message_id = provider_id
        message.sent_at = datetime.utcnow()
        db.flush()
    except Exception:
        transition(message.status, MessageStatus.failed, MESSAGE_TRANSITIONS, "message")
        message.status = MessageStatus.failed
        db.flush()
        raise
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
    # Also send queued messages with no schedule (immediate)
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
