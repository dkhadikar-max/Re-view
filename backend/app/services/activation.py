"""Signup -> first-real-value activation funnel (P4 onboarding audit, CTO P0).

North-star metric: signup_completed.created_at -> first_real_data_imported.
created_at, per tenant. Everything here exists to make that number
computable; nothing here changes product behavior.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import ActivationEvent, Property


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


def mark_real_data_imported(db: Session, *, tenant_id: str, property_: Property) -> None:
    """Called from import_reservation() (the single orchestrator every real
    importer -- manual, CSV, PDF -- goes through) once a real Guest/
    Reservation row has actually been created. Flips Property.has_real_data
    (hides the "Sample workspace" banner) and logs first_real_data_imported,
    both idempotently -- cheap to call on every imported row."""
    if not property_.has_real_data:
        property_.has_real_data = True
        db.add(property_)
    log_event_once(db, tenant_id=tenant_id, event_type="first_real_data_imported")
