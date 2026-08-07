"""Guest Service — the only code allowed to find-or-create a Guest row.

Every importer (manual entry, CSV, and future PDF/email/PMS connectors)
goes through this instead of writing to the Guest table directly. Keeps
guest deduplication-by-email consistent everywhere, once, instead of each
import path re-implementing (and subtly disagreeing on) the same logic.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Guest
from app.schemas import ReservationCreate


def find_or_create_guest(
    db: Session,
    tenant_id: str,
    property_id: str,
    payload: ReservationCreate,
) -> tuple[Guest, bool]:
    """Find an existing guest by (tenant, email) or create one.

    Returns (guest, created). On a match, updates the guest's stay count and
    spend from this reservation rather than creating a duplicate profile —
    email is the guest identity key across every import source.
    """
    guest: Guest | None = None
    if payload.guest_email:
        guest = (
            db.query(Guest)
            .filter(
                Guest.tenant_id == tenant_id,
                func.lower(Guest.email) == str(payload.guest_email).lower(),
            )
            .first()
        )

    if guest is not None:
        previous_stays = guest.stay_count
        guest.name = payload.guest_name
        guest.phone = payload.guest_phone or guest.phone
        guest.country = payload.country or guest.country
        guest.language = payload.language or guest.language
        guest.travel_type = payload.travel_type or guest.travel_type
        guest.purpose = payload.purpose or guest.purpose
        guest.communication_preference = (
            payload.communication_preference or guest.communication_preference
        )
        guest.stay_count = previous_stays + 1
        guest.lifetime_spend = float(guest.lifetime_spend or 0) + payload.total_amount
        guest.average_booking = (
            float(guest.lifetime_spend) / guest.stay_count
            if guest.stay_count
            else payload.total_amount
        )
        return guest, False

    guest = Guest(
        tenant_id=tenant_id,
        property_id=property_id,
        name=payload.guest_name,
        email=str(payload.guest_email) if payload.guest_email else None,
        phone=payload.guest_phone,
        country=payload.country,
        language=payload.language,
        travel_type=payload.travel_type,
        purpose=payload.purpose,
        children=payload.children,
        communication_preference=payload.communication_preference,
        stay_count=1,
        lifetime_spend=payload.total_amount,
        average_booking=payload.total_amount,
        ltv_score=50.0,
        satisfaction_score=70.0,
    )
    db.add(guest)
    db.flush()
    return guest, True
