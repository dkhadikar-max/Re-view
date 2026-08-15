from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.base import NormalizedReservation
from app.integrations.cloudbeds import CloudbedsClient, cloudbeds_client
from app.models.entities import (
    Connector,
    Guest,
    Property,
    Reservation,
    ReservationStatus,
)
from app.services.activation import mark_real_data_imported
from app.services.connectors import store_connector_secret
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "confirmed": ReservationStatus.confirmed,
    "checked_in": ReservationStatus.checked_in,
    "checked_out": ReservationStatus.checked_out,
    "cancelled": ReservationStatus.cancelled,
}


def sync_cloudbeds(
    db: Session,
    tenant_id: str,
    *,
    client: CloudbedsClient | None = None,
) -> dict[str, Any]:
    client = client or cloudbeds_client

    # P4 onboarding audit (CTO P0) -- "kill the fake PMS sync." No real
    # Cloudbeds credentials exist for any trial hotel today (Client ID/
    # secret and API key are all blank until real OAuth ships, P2). Do not
    # create or mark a Connector "connected", and do not write a single
    # Guest/Reservation row, on an unconfigured client -- that's exactly
    # what previously produced "Synced 2 reservations from Cloudbeds" for
    # a connection that was never made. Return honestly and stop here.
    if not client.configured:
        return {
            "imported": 0,
            "updated": 0,
            "events_emitted": 0,
            "cursor": None,
            "mode": "mock",
            "connected": False,
            "message": (
                "This trial isn't connected to a live Cloudbeds account yet. "
                "Import your real reservations via CSV, PDF, or manual entry."
            ),
        }

    connector = (
        db.query(Connector)
        .filter(Connector.tenant_id == tenant_id, Connector.provider == "Cloudbeds")
        .first()
    )
    if not connector:
        connector = Connector(
            tenant_id=tenant_id,
            provider="Cloudbeds",
            status="connected",
            config_encrypted=store_connector_secret("cloudbeds"),
            sync_cursor="0",
        )
        db.add(connector)
        db.flush()

    prop = db.query(Property).filter(Property.tenant_id == tenant_id).first()
    if not prop:
        raise ValueError("No property configured")

    rows, new_cursor = client.fetch_reservations(cursor=connector.sync_cursor)
    imported = 0
    updated = 0
    events = 0

    for row in rows:
        existing = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.source == "Cloudbeds",
                Reservation.external_id == row.external_id,
            )
            .first()
        )
        guest = _upsert_guest(db, tenant_id, prop.id, row)
        status = STATUS_MAP.get(row.status, ReservationStatus.confirmed)

        if existing:
            existing.status = status
            existing.room_type = row.room_type
            existing.check_in = row.check_in
            existing.check_out = row.check_out
            existing.total_amount = row.total_amount
            existing.updated_at = datetime.utcnow()
            updated += 1
            if status == ReservationStatus.checked_in:
                event_bus.publish_and_process(
                    db,
                    tenant_id,
                    "GuestCheckedIn",
                    {
                        "reservation_id": existing.id,
                        "guest_id": guest.id,
                        "external_id": row.external_id,
                    },
                    source="cloudbeds",
                    idempotency_key=f"GuestCheckedIn:Cloudbeds:{row.external_id}",
                )
                events += 1
            elif status == ReservationStatus.checked_out:
                event_bus.publish_and_process(
                    db,
                    tenant_id,
                    "GuestCheckedOut",
                    {
                        "reservation_id": existing.id,
                        "guest_id": guest.id,
                        "external_id": row.external_id,
                    },
                    source="cloudbeds",
                    idempotency_key=f"GuestCheckedOut:Cloudbeds:{row.external_id}",
                )
                events += 1
            continue

        res = Reservation(
            tenant_id=tenant_id,
            property_id=prop.id,
            guest_id=guest.id,
            external_id=row.external_id,
            source="Cloudbeds",
            status=status,
            room_type=row.room_type,
            check_in=row.check_in,
            check_out=row.check_out,
            adults=row.adults,
            children=row.children,
            total_amount=row.total_amount,
            currency=row.currency,
            special_requests=row.special_requests,
        )
        db.add(res)
        db.flush()
        event_bus.publish_and_process(
            db,
            tenant_id,
            "ReservationCreated",
            {
                "reservation_id": res.id,
                "guest_id": guest.id,
                "property_id": prop.id,
                "external_id": row.external_id,
            },
            source="cloudbeds",
            idempotency_key=f"ReservationCreated:Cloudbeds:{row.external_id}",
        )
        imported += 1
        events += 1

    connector.sync_cursor = new_cursor or connector.sync_cursor
    connector.last_sync_at = datetime.utcnow()
    connector.status = "connected"
    connector.last_error = None
    if imported > 0:
        # Bypasses import_reservation() (this path writes Reservation rows
        # directly, pre-dating the shared orchestrator) -- call the
        # activation hook directly so a genuine Cloudbeds sync still counts
        # toward "real data imported" like every other import path does.
        mark_real_data_imported(db, tenant_id=tenant_id, property_=prop)
    db.flush()
    return {
        "imported": imported,
        "updated": updated,
        "events_emitted": events,
        "cursor": connector.sync_cursor,
        "mode": client.mode,
        "connected": True,
        "message": f"Synced {imported} reservation(s) from Cloudbeds ({updated} updated).",
    }


def _upsert_guest(
    db: Session, tenant_id: str, property_id: str, row: NormalizedReservation
) -> Guest:
    guest = None
    if row.guest.email:
        guest = (
            db.query(Guest)
            .filter(Guest.tenant_id == tenant_id, Guest.email == row.guest.email)
            .first()
        )
    if not guest and row.guest.phone:
        guest = (
            db.query(Guest)
            .filter(Guest.tenant_id == tenant_id, Guest.phone == row.guest.phone)
            .first()
        )
    if guest:
        guest.name = row.guest.name or guest.name
        guest.phone = row.guest.phone or guest.phone
        guest.country = row.guest.country or guest.country
        guest.language = row.guest.language or guest.language
        guest.updated_at = datetime.utcnow()
        db.flush()
        return guest

    guest = Guest(
        tenant_id=tenant_id,
        property_id=property_id,
        name=row.guest.name,
        email=row.guest.email,
        phone=row.guest.phone,
        country=row.guest.country,
        language=row.guest.language or "en",
        children=row.children,
        communication_preference="whatsapp" if row.guest.phone else "email",
        stay_count=1,
        lifetime_spend=row.total_amount,
        average_booking=row.total_amount,
        ltv_score=55,
        satisfaction_score=70,
    )
    db.add(guest)
    db.flush()
    return guest


def cloudbeds_check_in(db: Session, tenant_id: str, reservation_id: str) -> dict[str, Any]:
    reservation = (
        db.query(Reservation)
        .filter(Reservation.id == reservation_id, Reservation.tenant_id == tenant_id)
        .first()
    )
    if not reservation:
        raise ValueError("Reservation not found")
    if reservation.external_id:
        cloudbeds_client.check_in(reservation.external_id)
    reservation.status = ReservationStatus.checked_in
    event_bus.publish_and_process(
        db,
        tenant_id,
        "GuestCheckedIn",
        {"reservation_id": reservation.id, "guest_id": reservation.guest_id},
        source="cloudbeds",
        idempotency_key=f"GuestCheckedIn:{reservation.id}",
    )
    db.flush()
    return {"ok": True, "status": "checked_in"}


def cloudbeds_check_out(db: Session, tenant_id: str, reservation_id: str) -> dict[str, Any]:
    reservation = (
        db.query(Reservation)
        .filter(Reservation.id == reservation_id, Reservation.tenant_id == tenant_id)
        .first()
    )
    if not reservation:
        raise ValueError("Reservation not found")
    if reservation.external_id:
        cloudbeds_client.check_out(reservation.external_id)
    reservation.status = ReservationStatus.checked_out
    event_bus.publish_and_process(
        db,
        tenant_id,
        "GuestCheckedOut",
        {"reservation_id": reservation.id, "guest_id": reservation.guest_id},
        source="cloudbeds",
        idempotency_key=f"GuestCheckedOut:{reservation.id}",
    )
    db.flush()
    return {"ok": True, "status": "checked_out"}
