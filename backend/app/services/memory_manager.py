"""Memory Manager — MEMORY_MANAGER.md, the frozen v1 contract. The only
component allowed to write a memory update to a `Guest` row.

    MemoryManager.apply_or_hold(db, *, event, memory_updates) -> None

`GuestMemoryAgent` only ever proposes (`AgentResponse.metadata
["memory_updates"]`, a list of `{field, value, confidence}` dicts) —
it never touches the database (`guest_memory_agent.py`'s own
docstring). This module is the only place that ever calls
`setattr`/`db.add` on a `Guest` row for a memory update, and the only
place a `MEMORY_ACCEPTED`/`MEMORY_HELD`/`MEMORY_REJECTED` `ActionEvent`
gets logged.

See `MEMORY_MANAGER.md` (repo root) for the full frozen contract this
implements verbatim — confidence bands, field-specific mutation rules,
the Action Ledger taxonomy, the transactional guarantee, and
idempotency. Do not change this module's behavior without updating
that document first, the same discipline CONCIERGE.md's own frozen
contracts (`action_type`, `actor`) already require.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    ActionEvent,
    ActionEventStatus,
    ActorType,
    Guest,
    Task,
    TaskPriority,
    TaskStatus,
)
from app.services.action_logger import action_logger

# MEMORY_MANAGER.md §2 — fixed bands, not a computed score, same
# "deterministic, not a model score" discipline every other component
# in this codebase already uses.
_AUTO_APPLY_THRESHOLD = 0.85
_HOLD_THRESHOLD = 0.70

# MEMORY_MANAGER.md §4 — a new, deliberately documented action_type
# addition to CONCIERGE.md's frozen v1 taxonomy (CONCIERGE.md §15).
# MEMORY_HELD is kept distinct from MEMORY_REJECTED on purpose:
# "policy decided not to accept" and "policy deferred to a human" are
# different training signals for Argus, not one ambiguous outcome.
_ACTION_TYPE_ACCEPTED = "MEMORY_ACCEPTED"
_ACTION_TYPE_REJECTED = "MEMORY_REJECTED"
_ACTION_TYPE_HELD = "MEMORY_HELD"


def _apply_dietary(guest: Guest, value: str) -> str:
    """MEMORY_MANAGER.md §3 — protected. Never silently replaces an
    existing value at any confidence; only ever appends a genuinely new
    fact, or is ignored as a duplicate. No semantic relationship is
    inferred between values — a "Vegan" proposal never collapses into
    an existing "Vegetarian" one — this stores the guest's own words
    verbatim and leaves normalization to staff.
    """
    existing = guest.dietary_preferences
    if not existing:
        guest.dietary_preferences = value
        return "applied"
    if value.strip().lower() in existing.lower():
        return "duplicate_ignored"
    guest.dietary_preferences = f"{existing}; {value}"
    return "applied"


def _apply_preferred_room(guest: Guest, value: str) -> str:
    """MEMORY_MANAGER.md §3 — not protected. The guest's most recently
    and explicitly stated preference replaces whatever was there,
    gated only by the ≥0.85 confidence band this is already called
    from — a wrong room preference costs nothing like a wrong dietary
    fact does."""
    if guest.preferred_room and guest.preferred_room.strip().lower() == value.strip().lower():
        return "duplicate_ignored"
    guest.preferred_room = value
    return "applied"


def _apply_notes(guest: Guest, value: str) -> str:
    """MEMORY_MANAGER.md §3 — append-only, timestamped. §6's general
    idempotency guarantee ("re-proposing the same fact must not create
    a duplicate") still applies here: "always append" in the frozen
    spec means always append a genuinely new note, not append every
    resubmission of an identical one.
    """
    if guest.notes and value.strip().lower() in guest.notes.lower():
        return "duplicate_ignored"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d")
    entry = f"[{timestamp}] {value}"
    guest.notes = f"{guest.notes}\n{entry}" if guest.notes else entry
    return "applied"


_FIELD_HANDLERS: dict[str, Callable[[Guest, str], str]] = {
    "dietary_preferences": _apply_dietary,
    "preferred_room": _apply_preferred_room,
    "notes": _apply_notes,
}


class MemoryManager:
    """Stateless — holds no data between calls, same as every other
    manager/agent in this codebase. One instance is safe to reuse
    across every tenant, guest, and turn."""

    def apply_or_hold(
        self, db: Session, *, event: ActionEvent, memory_updates: list[dict[str, Any]]
    ) -> None:
        """Called by the Router right after it logs `MEMORY_PROPOSED`
        (`event`) for a `GuestMemoryAgent` response. A single turn can
        propose more than one field (e.g. a dietary fact plus a room
        preference in the same message) — each is independently
        confidence-gated and logged as its own `ActionEvent`, sharing
        `event`'s own `correlation_id` (MEMORY_MANAGER.md §4/§8).
        """
        guest = self._load_guest(db, event)
        if guest is None:
            return
        for update in memory_updates:
            self._apply_one(
                db,
                event=event,
                guest=guest,
                field=update["field"],
                value=update["value"],
                confidence=update["confidence"],
                # Phase 4A (GUEST_MEMORY_EVIDENCE_CHAIN.md §3) — absent
                # for any update dict built before this field existed
                # (e.g. a synthetic test case), so this is always a
                # tolerant .get, never a required key.
                message_id=update.get("message_id"),
            )

    def _load_guest(self, db: Session, event: ActionEvent) -> Optional[Guest]:
        # MEMORY_MANAGER.md §7 — tenant-scoped by construction, no
        # generic cross-tenant query surface exists anywhere in this
        # module.
        return (
            db.query(Guest)
            .filter(Guest.id == event.guest_id, Guest.tenant_id == event.tenant_id)
            .first()
        )

    def _apply_one(
        self,
        db: Session,
        *,
        event: ActionEvent,
        guest: Guest,
        field: str,
        value: str,
        confidence: float,
        message_id: Optional[str] = None,
    ) -> None:
        if confidence < _HOLD_THRESHOLD:
            self._reject(
                db, event, field=field, confidence=confidence,
                reason="confidence_below_threshold",
            )
            return
        if confidence < _AUTO_APPLY_THRESHOLD:
            self._hold(db, event, guest=guest, field=field, confidence=confidence)
            return

        handler = _FIELD_HANDLERS.get(field)
        if handler is None:
            # An unrecognized field is a caller bug — GuestMemoryAgent
            # and this module's field list are meant to stay in sync —
            # not something a guest's own message can trigger. Refuse
            # rather than guess how to mutate an unknown column.
            self._reject(
                db, event, field=field, confidence=confidence, reason="unrecognized_field",
            )
            return

        outcome = handler(guest, value)
        if outcome == "duplicate_ignored":
            self._reject(
                db, event, field=field, confidence=confidence, reason="duplicate_ignored",
            )
            return

        # MEMORY_MANAGER.md §5 — the Guest mutation above and this
        # ActionEvent are the same database transaction: both are only
        # ever flushed here, never committed by this module, so
        # whatever ultimately commits this request's session commits
        # (or rolls back) them together.
        db.flush()
        action_logger.log_action(
            db,
            tenant_id=event.tenant_id,
            guest_id=event.guest_id,
            reservation_id=event.reservation_id,
            conversation_id=event.conversation_id,
            correlation_id=event.correlation_id,
            intent=event.intent,
            agent=None,
            action_type=_ACTION_TYPE_ACCEPTED,
            actor=ActorType.system,
            confidence=confidence,
            input_summary=f"Guest memory proposal for {field}.",
            decision=f"Applied to Guest.{field}.",
            status=ActionEventStatus.accepted,
            # Phase 4A (GUEST_MEMORY_EVIDENCE_CHAIN.md §3) — the one
            # addition this phase makes to the frozen §4 metadata shape.
            # Still never the guest's raw text (MEMORY_MANAGER.md §4's
            # own rule, unchanged) — just the id of the Message a reader
            # can join to later if it wants the actual quote.
            metadata={"field": field, "reason": "applied", "message_id": message_id},
        )

    def _hold(
        self, db: Session, event: ActionEvent, *, guest: Guest, field: str, confidence: float
    ) -> None:
        # No PMS/CRM integration exists to apply a lower-confidence
        # memory update automatically — a staff Task is the only
        # execution path, same reasoning Conversation Manager's own
        # OFFER_ACCEPTED -> TASK_CREATED path already uses.
        readable_field = field.replace("_", " ")
        task = Task(
            tenant_id=event.tenant_id,
            title=f"Review possible {readable_field} update: {guest.name}",
            description=(
                f"GuestMemoryAgent proposed a {readable_field} update with "
                f"confidence {confidence:.2f} — below the auto-apply threshold. "
                "A staff member should review and apply it manually if correct."
            ),
            status=TaskStatus.open,
            priority=TaskPriority.medium,
            related_type="guest",
            related_id=guest.id,
            # PILOT_READINESS.md §5 — same id as the MEMORY_PROPOSED/
            # MEMORY_HELD events, so staff completion (TASK_COMPLETED)
            # rejoins the same chain.
            correlation_id=event.correlation_id,
        )
        db.add(task)
        db.flush()
        action_logger.log_action(
            db,
            tenant_id=event.tenant_id,
            guest_id=event.guest_id,
            reservation_id=event.reservation_id,
            conversation_id=event.conversation_id,
            correlation_id=event.correlation_id,
            intent=event.intent,
            agent=None,
            action_type=_ACTION_TYPE_HELD,
            actor=ActorType.system,
            confidence=confidence,
            input_summary=f"Guest memory proposal for {field} held for review.",
            decision="Confidence below auto-apply threshold; created staff Task.",
            status=ActionEventStatus.escalated,
            metadata={
                "field": field,
                "reason": "confidence_below_threshold",
                "task_id": task.id,
            },
        )

    def _reject(
        self, db: Session, event: ActionEvent, *, field: str, confidence: float, reason: str
    ) -> None:
        action_logger.log_action(
            db,
            tenant_id=event.tenant_id,
            guest_id=event.guest_id,
            reservation_id=event.reservation_id,
            conversation_id=event.conversation_id,
            correlation_id=event.correlation_id,
            intent=event.intent,
            agent=None,
            action_type=_ACTION_TYPE_REJECTED,
            actor=ActorType.system,
            confidence=confidence,
            input_summary=f"Guest memory proposal for {field} not applied.",
            decision=f"Not applied: {reason}.",
            status=ActionEventStatus.rejected,
            metadata={"field": field, "reason": reason},
        )


memory_manager = MemoryManager()
