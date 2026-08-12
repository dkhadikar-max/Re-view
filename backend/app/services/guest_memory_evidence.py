"""Guest Memory Evidence — Phase 4A, GUEST_MEMORY_EVIDENCE_CHAIN.md.

Read-only. Answers "what does ReVisit currently remember about this
guest, and where did it come from" by walking the existing Action
Ledger — it does not introduce a second data model alongside
MEMORY_MANAGER.md's Guest columns (`dietary_preferences`,
`preferred_room`), and it never mutates anything.

    get_guest_memory_evidence(db, *, tenant_id, guest_id) -> list[MemoryEvidence]

v1 is confirmed-only by construction, matching
GUEST_MEMORY_EVIDENCE_CHAIN.md §2's recommendation: every
`MEMORY_ACCEPTED` event today came from `GuestMemoryAgent`'s one
evidence source (an explicit guest self-statement) — there is no
"inferred" branch to build here. That stays a documented, deferred
roadmap item ("Guest Memory: order-pattern evidence track"), not
something this module fakes.

`notes` is deliberately excluded from the evidence chain — it's an
append-only free-text log (MEMORY_MANAGER.md §3), not one current
value the way the other two fields are, so there's no single "the
preference" to attach evidence to without guessing which line matters.

GUEST_INSIGHT_CONTRACT.md (§1, frozen) — `category` is the one
addition this phase makes. Deterministic mapping from `field` only
(Clarification B); never backfilled from `notes` or any free-form
interpretation. The frozen contract's `needs_review` taxonomy state
is deliberately not produced anywhere in this module — see the
contract's "Open finding": no real, deterministic trigger for a
dietary conflict exists without a `GuestMemoryAgent` pattern change,
which is explicitly out of scope here.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.entities import ActionEvent, Guest, Message

_ACCEPTED_ACTION_TYPE = "MEMORY_ACCEPTED"

_FIELD_LABELS = {
    "dietary_preferences": "Dietary preference",
    "preferred_room": "Room preference",
}

# GUEST_INSIGHT_CONTRACT.md Clarification B — deterministic, from
# `field` only. A field not listed here gets `category=None`, never a
# guess derived from its value or from `notes`.
_FIELD_CATEGORIES = {
    "dietary_preferences": "Dining",
    "preferred_room": "Room",
}


class MemoryEvidence(BaseModel):
    model_config = {"frozen": True}

    field: str
    field_label: str
    value: str
    # Always True in v1 — see module docstring. Kept as an explicit
    # field (rather than assumed by the reader) so a future inferred
    # evidence source can set it False without every caller needing to
    # relearn what "confirmed" means.
    confirmed: bool
    evidence_quote: Optional[str]
    evidence_channel: Optional[str]
    evidence_date: Optional[str]  # ISO date, or None if no linked message
    insight: str
    hotel_intelligence: str
    # GUEST_INSIGHT_CONTRACT.md Clarification B. None for any field
    # not in _FIELD_CATEGORIES -- never backfilled from notes or any
    # free-form interpretation.
    category: Optional[str] = None


def _guest_insight(value: str) -> str:
    """Evidence-grounded synthesis, not a new inference engine — a
    fixed template over facts this module already has, the same
    "deterministic, not a model score" discipline every other
    component in this codebase uses.

    Deliberately does not claim a preference is "recurring": a guest
    repeating the exact same statement is caught by MEMORY_MANAGER.md
    §3/§6's own duplicate-detection and logged as MEMORY_REJECTED, not
    a second MEMORY_ACCEPTED — so "stated once" and "stated
    identically many times" are indistinguishable in the ledger today.
    Claiming "recurring" would be a real, checkable overclaim, not
    evidence-grounded synthesis.
    """
    return f"{value} is a confirmed preference. Based on the guest's previous explicit statement."


def _hotel_intelligence(field_label: str) -> str:
    return f"Keep this {field_label.lower()} visible to the relevant team throughout the stay."


def get_guest_memory_evidence(
    db: Session, *, tenant_id: str, guest_id: str
) -> list[MemoryEvidence]:
    guest = (
        db.query(Guest).filter(Guest.id == guest_id, Guest.tenant_id == tenant_id).first()
    )
    if guest is None:
        return []

    current_values = {
        "dietary_preferences": guest.dietary_preferences,
        "preferred_room": guest.preferred_room,
    }
    fields_with_values = {field: value for field, value in current_values.items() if value}
    if not fields_with_values:
        return []

    events = (
        db.query(ActionEvent)
        .filter(
            ActionEvent.tenant_id == tenant_id,
            ActionEvent.guest_id == guest_id,
            ActionEvent.action_type == _ACCEPTED_ACTION_TYPE,
        )
        .order_by(ActionEvent.created_at.asc())
        .all()
    )

    # field -> most recent accepted event for that field. A guest can
    # have multiple ACCEPTED events per field (dietary_preferences is
    # append-only, so a second event usually means a *different* fact
    # was added, e.g. an allergy after a diet) — the most recent one is
    # the best evidence for the field's *current* combined value.
    latest_event_by_field: dict[str, ActionEvent] = {}
    for event in events:
        try:
            meta = json.loads(event.event_metadata or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        field = meta.get("field")
        if field in fields_with_values:
            latest_event_by_field[field] = event

    results: list[MemoryEvidence] = []
    for field, value in fields_with_values.items():
        field_label = _FIELD_LABELS.get(field, field.replace("_", " ").title())
        quote = channel = evidence_date = None

        latest = latest_event_by_field.get(field)
        if latest is not None:
            try:
                meta = json.loads(latest.event_metadata or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
            message_id = meta.get("message_id")
            if message_id:
                message = (
                    db.query(Message)
                    .filter(Message.id == message_id, Message.tenant_id == tenant_id)
                    .first()
                )
                if message is not None:
                    quote = message.body
                    channel = message.channel.value if message.channel else None
                    evidence_date = (
                        message.created_at.date().isoformat() if message.created_at else None
                    )

        results.append(
            MemoryEvidence(
                field=field,
                field_label=field_label,
                value=value,
                confirmed=True,
                evidence_quote=quote,
                evidence_channel=channel,
                evidence_date=evidence_date,
                insight=_guest_insight(value),
                hotel_intelligence=_hotel_intelligence(field_label),
                category=_FIELD_CATEGORIES.get(field),
            )
        )
    return results
