from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.entities import Event


class EventBus:
    """In-process event bus for MVP. Swap for Redis Streams later."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(
        self,
        db: Session,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any],
        source: str = "system",
    ) -> Event:
        event = Event(
            tenant_id=tenant_id,
            event_type=event_type,
            payload=json.dumps(payload),
            source=source,
            processed=False,
            created_at=datetime.utcnow(),
        )
        db.add(event)
        db.flush()

        for handler in self._handlers.get(event_type, []):
            handler(db, event, payload)
        for handler in self._handlers.get("*", []):
            handler(db, event, payload)

        event.processed = True
        db.flush()
        return event


event_bus = EventBus()
