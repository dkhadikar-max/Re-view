"""Import Orchestrator — the single entry point every reservation-import
source must go through.

    Importer -> Normalizer -> Validator -> Import Orchestrator
                                                |
                                                v
                                   Guest Service -> Reservation Service
                                                |
                                                v
                                       Automation Engine (event bus)

No importer writes Guest or Reservation rows directly. Today's importers are
manual entry (routes.create_reservation) and CSV (routes.import_csv), each
already producing a validated `ReservationCreate` (the Validator stage).
Future importers (PDF extraction, email ingestion, PMS connectors) only need
to produce the same `ReservationCreate` shape and call `import_reservation`
below — orchestration, dedup, and automation stay written once, here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    Guest,
    ImportSession,
    ImportSessionStatus,
    Message,
    Offer,
    Reservation,
)
from app.schemas import ReservationCreate
from app.services.event_bus import event_bus
from app.services.guest_service import find_or_create_guest
from app.services.reservation_service import create_reservation_record


def start_import_session(
    db: Session,
    *,
    tenant_id: str,
    source: str,
    initiated_by: str,
    rows_total: int = 0,
) -> ImportSession:
    session = ImportSession(
        tenant_id=tenant_id,
        source=source,
        status=ImportSessionStatus.running,
        rows_total=rows_total,
        initiated_by=initiated_by,
    )
    db.add(session)
    db.flush()
    return session


def finish_import_session(db: Session, session: ImportSession) -> ImportSession:
    session.status = (
        ImportSessionStatus.completed
        if session.rows_failed == 0 and session.rows_skipped == 0
        else ImportSessionStatus.completed_with_errors
    )
    session.completed_at = datetime.utcnow()
    db.flush()
    return session


def import_reservation(
    db: Session,
    *,
    tenant_id: str,
    property_id: str,
    payload: ReservationCreate,
    external_id: str,
    event_source: str,
    import_session: Optional[ImportSession] = None,
) -> tuple[Guest, Reservation, bool]:
    """Turn one validated `ReservationCreate` into Guest + Reservation rows
    and fire the same automation every existing path already relies on.

    `event_source` labels who triggered this for the event/audit trail
    (e.g. "api" for manual entry, "csv" for CSV import) — distinct from
    `payload.source`, which is the reservation's own booking-channel field
    (e.g. "direct"). Keeping these separate preserves each import path's
    existing event-log values exactly.

    Returns (guest, reservation, guest_created).
    """
    guest, created = find_or_create_guest(db, tenant_id, property_id, payload)
    reservation = create_reservation_record(
        db,
        tenant_id=tenant_id,
        property_id=property_id,
        guest_id=guest.id,
        external_id=external_id,
        payload=payload,
    )

    if import_session is not None:
        reservation.import_session_id = import_session.id
        import_session.rows_imported += 1

    if created:
        event_bus.publish_and_process(
            db,
            tenant_id,
            "GuestProfileCreated",
            {"guest_id": guest.id, "property_id": property_id},
            source=event_source,
            idempotency_key=f"GuestProfileCreated:{guest.id}",
        )
    event_bus.publish_and_process(
        db,
        tenant_id,
        "ReservationCreated",
        {
            "reservation_id": reservation.id,
            "guest_id": guest.id,
            "property_id": property_id,
        },
        source=event_source,
        idempotency_key=f"ReservationCreated:{event_source}:{external_id}",
    )
    return guest, reservation, created


def build_import_summary(db: Session, session: ImportSession) -> dict[str, Any]:
    """Compute the "so what" numbers for the Import Summary screen from data
    the import already produced — no separate tracking needed.

    A guest counts as "created" if this session accounts for their entire
    stay_count (they had no history before this import), otherwise they're
    "returning". Reviews/upsells are read from the Messages/Offers the
    Automation Engine already created via the ReservationCreated event that
    import_reservation() fires per row — this reuses existing automation,
    it doesn't add any.
    """
    reservations = (
        db.query(Reservation)
        .filter(Reservation.import_session_id == session.id)
        .all()
    )
    reservation_ids = [r.id for r in reservations]

    reservations_per_guest: dict[str, int] = {}
    for r in reservations:
        reservations_per_guest[r.guest_id] = reservations_per_guest.get(r.guest_id, 0) + 1

    guests = (
        db.query(Guest).filter(Guest.id.in_(reservations_per_guest.keys())).all()
        if reservations_per_guest
        else []
    )
    today = date.today()
    guests_created = 0
    returning_guests = 0
    birthdays_this_month = 0
    for guest in guests:
        if guest.stay_count <= reservations_per_guest.get(guest.id, 0):
            guests_created += 1
        else:
            returning_guests += 1
        if guest.birthday and guest.birthday.month == today.month:
            birthdays_this_month += 1

    reviews_scheduled = (
        db.query(Message)
        .filter(
            Message.reservation_id.in_(reservation_ids),
            Message.message_type == "review_request",
        )
        .count()
        if reservation_ids
        else 0
    )
    upsell_opportunities = (
        db.query(Offer).filter(Offer.reservation_id.in_(reservation_ids)).count()
        if reservation_ids
        else 0
    )

    return {
        "reservations_imported": session.rows_imported,
        "guests_created": guests_created,
        "returning_guests": returning_guests,
        "birthdays_this_month": birthdays_this_month,
        "reviews_scheduled": reviews_scheduled,
        "upsell_opportunities": upsell_opportunities,
    }
