"""Reservation Service — the only code allowed to create a Reservation row.

Paired with guest_service.find_or_create_guest and orchestrated by
import_orchestrator.import_reservation. No importer writes to the
Reservation table directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import Reservation, ReservationStatus
from app.schemas import ReservationCreate


def create_reservation_record(
    db: Session,
    *,
    tenant_id: str,
    property_id: str,
    guest_id: str,
    external_id: str,
    payload: ReservationCreate,
) -> Reservation:
    reservation = Reservation(
        tenant_id=tenant_id,
        property_id=property_id,
        guest_id=guest_id,
        external_id=external_id,
        source=payload.source,
        status=ReservationStatus.confirmed,
        room_type=payload.room_type,
        check_in=payload.check_in,
        check_out=payload.check_out,
        adults=payload.adults,
        children=payload.children,
        total_amount=payload.total_amount,
        currency=payload.currency.upper(),
        special_requests=payload.special_requests,
    )
    db.add(reservation)
    db.flush()
    return reservation
