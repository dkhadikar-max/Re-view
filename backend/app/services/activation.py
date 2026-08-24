"""Signup -> first-real-value activation funnel (P4 onboarding audit, CTO P0).

North-star metric: signup_completed.created_at -> first_real_data_imported.
created_at, per tenant. Everything here exists to make that number
computable; nothing here changes product behavior.

CTO P0 (code-review follow-up): telemetry must never be able to block a
real business action (signup, login, approvals, imports). Every call
site outside this module uses `safe_log_event_once()`, never `log_event`/
`log_event_once` directly -- see that function's docstring for why a
plain try/except around a shared-session write isn't enough on its own.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import ActivationEvent, Property

logger = logging.getLogger(__name__)


def log_event(
    db: Session,
    *,
    tenant_id: Optional[str],
    event_type: str,
    metadata: Optional[dict[str, Any]] = None,
) -> ActivationEvent:
    """Always inserts a row -- for events with no natural "first" (today
    just `signup_started`, fired once per page view, pre-account)."""
    entry = ActivationEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        event_metadata=json.dumps(metadata) if metadata else None,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    return entry


def log_event_once(
    db: Session,
    *,
    tenant_id: str,
    event_type: str,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[ActivationEvent]:
    """Writes the event only if this tenant has never logged this
    event_type before -- keeps the funnel's timestamps meaning "the first
    time this happened," not "the most recent." No-op (returns None) on
    a repeat call, so call sites can call this unconditionally on every
    request without needing their own guard."""
    exists = (
        db.query(ActivationEvent.id)
        .filter(
            ActivationEvent.tenant_id == tenant_id,
            ActivationEvent.event_type == event_type,
        )
        .first()
    )
    if exists:
        return None
    return log_event(db, tenant_id=tenant_id, event_type=event_type, metadata=metadata)


def safe_log_event_once(
    db: Session,
    *,
    tenant_id: str,
    event_type: str,
    metadata: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> None:
    """Best-effort wrapper around `log_event_once()` -- NEVER raises, and
    never corrupts the caller's own transaction.

    CTO P0: telemetry must never block a real business action. A plain
    try/except around `log_event_once()` isn't sufficient on its own: it
    shares the caller's `db` Session, and SQLAlchemy poisons a Session
    after any failed flush/insert -- every operation on it (including the
    caller's own later `db.commit()` for the REAL business logic) then
    raises `PendingRollbackError` until something calls `db.rollback()`.
    Wrapping the write in a SAVEPOINT (`db.begin_nested()`) means a
    failure here rolls back only this write, not anything the caller has
    already staged in the same session.

    Callers must call this AFTER their own business action has completed
    (ideally after their own commit) -- never before it -- so a slow or
    failing telemetry write can't delay or block the action it's
    measuring. See CTO note: "Business action -> commit -> best-effort
    telemetry -> never block the user."

    `commit=True` (the default, for every route-level call site) makes
    this fully self-contained: the caller's own business commit has
    already happened by the time this runs, so this issues its own small,
    separate commit for durability -- no call site needs to remember
    "commit or not" itself (the exact inconsistency the code review
    flagged). Pass `commit=False` only when the event must ride along
    with an enclosing, still-open transaction that hasn't committed yet
    (mark_real_data_imported, called mid-loop from inside a still-running
    import) -- there, committing early would prematurely persist a
    partially-completed import.
    """
    try:
        with db.begin_nested():
            log_event_once(db, tenant_id=tenant_id, event_type=event_type, metadata=metadata)
        if commit:
            db.commit()
    except Exception:
        logger.exception(
            "activation event logging failed (ignored, business action unaffected): "
            "tenant=%s event=%s",
            tenant_id,
            event_type,
        )
        if commit:
            try:
                db.rollback()
            except Exception:
                pass


def mark_real_data_imported(db: Session, *, tenant_id: str, property_: Property) -> None:
    """Called from import_reservation() (the single orchestrator every real
    importer -- manual, CSV, PDF -- goes through) once a real Guest/
    Reservation row has actually been created. Flips Property.has_real_data
    (hides the "Sample workspace" banner) -- real product state, kept in
    the caller's own transaction, not best-effort -- and logs
    first_real_data_imported via the best-effort wrapper.

    The event log is only attempted on the actual False->True flip, not on
    every row of a multi-row import: once has_real_data is already True,
    logging again would just be a wasted no-op query (log_event_once's own
    idempotency would still no-op it, but re-querying activation_events
    once per CSV row for up to csv_max_rows rows is pure waste for no
    behavior change)."""
    if not property_.has_real_data:
        property_.has_real_data = True
        db.add(property_)
        # commit=False: this runs mid-loop, inside a still-open import
        # transaction (import_reservation() may be called many times before
        # the route's own final commit) -- committing here would
        # prematurely persist a partially-completed multi-row import.
        safe_log_event_once(
            db, tenant_id=tenant_id, event_type="first_real_data_imported", commit=False
        )
