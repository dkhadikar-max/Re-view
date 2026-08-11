"""Pilot operational visibility — PILOT_READINESS.md §4.

    pilot_health(db, *, tenant_id, hours=24) -> PilotHealthOut

Deliberately **not** a full observability platform: one tenant-scoped
summary of the five conditions the design doc identifies, queryable
without reading raw server logs. No new alerting/email/webhook
infrastructure — the mechanism is a single aggregate endpoint, exactly
what the doc's §4 left open for this implementation to decide.

Each count below maps to one of the five gaps in PILOT_READINESS.md §4:

1. Failed inbound processing — `Message.processing_failed`, set by
   `messaging.py` when a `TranslationError`/`ContextBuilderError`
   caused the Concierge Router to be skipped for that turn.
2. Translation failures specifically — a subset of the above (inbound)
   plus outbound translation failures, distinguished from an ordinary
   WhatsApp delivery/API failure via `Message.failure_reason`.
3. Outbound delivery failures — split into still-retriable (`failed`,
   under the retry cap from PILOT_READINESS.md §2) and exhausted
   (`failed`, at the cap) — only the exhausted ones are the "someone
   should look at this" signal; a fresh `failed` message may still
   self-heal on the next retry pass.
4. Duplicate webhook detection — `Message.duplicate_webhook_count`,
   incremented by the §1 dedup check every time it short-circuits a
   replayed webhook. The system already handles these correctly; a
   spike is still worth knowing about (usually a Meta-side delivery
   problem, not a ReVisit bug).
5. Stale open staff Tasks — `Task.status == open` older than the
   lookback window, connecting directly to the evidence-chain gap
   found while writing §5 (task completion has no ledger record yet,
   so "is anyone actually working this" has no other visibility today).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.entities import Message, MessageStatus, Task, TaskStatus
from app.services.messaging import MAX_OUTBOUND_RETRIES

# Failure reasons set on Message.failure_reason that specifically
# indicate a translation failure (inbound normalization or outbound
# response translation) rather than a generic delivery/API failure —
# see messaging.py's TranslationError handlers.
_TRANSLATION_FAILURE_REASONS = ("translation_error", "outbound_translation_error")


class PilotHealthOut(BaseModel):
    window_hours: int
    inbound_processing_failures: int
    translation_failures: int
    outbound_delivery_failed_active: int
    outbound_delivery_exhausted: int
    duplicate_webhooks_detected: int
    stale_open_tasks: int


def pilot_health(db: Session, *, tenant_id: str, hours: int = 24) -> PilotHealthOut:
    since = datetime.utcnow() - timedelta(hours=hours)

    inbound_processing_failures = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.processing_failed.is_(True),
            Message.created_at >= since,
        )
        .count()
    )
    translation_failures = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.failure_reason.in_(_TRANSLATION_FAILURE_REASONS),
            Message.created_at >= since,
        )
        .count()
    )
    outbound_delivery_failed_active = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.direction == "outbound",
            Message.status == MessageStatus.failed,
            Message.retry_count < MAX_OUTBOUND_RETRIES,
            Message.created_at >= since,
        )
        .count()
    )
    outbound_delivery_exhausted = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.direction == "outbound",
            Message.status == MessageStatus.failed,
            Message.retry_count >= MAX_OUTBOUND_RETRIES,
            Message.created_at >= since,
        )
        .count()
    )
    duplicate_webhooks_detected = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.duplicate_webhook_count > 0,
            Message.created_at >= since,
        )
        .count()
    )
    stale_open_tasks = (
        db.query(Task)
        .filter(
            Task.tenant_id == tenant_id,
            Task.status == TaskStatus.open,
            Task.created_at < since,
        )
        .count()
    )

    return PilotHealthOut(
        window_hours=hours,
        inbound_processing_failures=inbound_processing_failures,
        translation_failures=translation_failures,
        outbound_delivery_failed_active=outbound_delivery_failed_active,
        outbound_delivery_exhausted=outbound_delivery_exhausted,
        duplicate_webhooks_detected=duplicate_webhooks_detected,
        stale_open_tasks=stale_open_tasks,
    )
