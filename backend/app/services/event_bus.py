from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models.entities import Event, EventStatus

logger = logging.getLogger(__name__)

Handler = Callable[[Session, Event, dict[str, Any]], None]


class EventBus:
    """Transactional outbox-style bus.

    publish() persists an event as pending. process_pending() / process_event()
    runs handlers with retries. For request-path UX, publish_and_process()
    processes immediately after insert in the same session.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> None:
        handlers = self._handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def reset(self) -> None:
        self._handlers.clear()

    def publish(
        self,
        db: Session,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any],
        source: str = "system",
        idempotency_key: Optional[str] = None,
    ) -> Event:
        if idempotency_key:
            existing = (
                db.query(Event)
                .filter(
                    Event.tenant_id == tenant_id,
                    Event.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing:
                return existing

        event = Event(
            tenant_id=tenant_id,
            event_type=event_type,
            payload=json.dumps(payload),
            source=source,
            status=EventStatus.pending,
            processed=False,
            attempts=0,
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow(),
        )
        db.add(event)
        db.flush()
        return event

    def publish_and_process(
        self,
        db: Session,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any],
        source: str = "system",
        idempotency_key: Optional[str] = None,
    ) -> Event:
        event = self.publish(
            db, tenant_id, event_type, payload, source, idempotency_key
        )
        if event.status == EventStatus.pending:
            self.process_event(db, event)
        return event

    def process_event(self, db: Session, event: Event) -> Event:
        if event.status == EventStatus.processed:
            return event

        event.status = EventStatus.processing
        event.attempts += 1
        db.flush()

        try:
            payload = json.loads(event.payload or "{}")
            for handler in self._handlers.get(event.event_type, []):
                handler(db, event, payload)
            for handler in self._handlers.get("*", []):
                handler(db, event, payload)
            event.status = EventStatus.processed
            event.processed = True
            event.processed_at = datetime.utcnow()
            event.last_error = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Event handler failed for %s", event.id)
            event.status = EventStatus.failed
            event.processed = False
            event.last_error = str(exc)
            if event.attempts < 3:
                event.status = EventStatus.pending
        db.flush()
        return event

    def process_pending(self, db: Session, limit: int = 50) -> int:
        events = (
            db.query(Event)
            .filter(Event.status == EventStatus.pending)
            .order_by(Event.created_at.asc())
            .limit(limit)
            .all()
        )
        count = 0
        for event in events:
            self.process_event(db, event)
            count += 1
        return count


event_bus = EventBus()
