from __future__ import annotations

import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    Connector,
    Guest,
    Property,
    Reservation,
    ReservationStatus,
)
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)


def _seal(plaintext: str) -> str:
    """Lightweight credential seal for MVP (replace with KMS in production)."""
    digest = hashlib.sha256((settings.jwt_secret + plaintext).encode()).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{digest}:{plaintext}".encode()).decode()


def store_connector_secret(raw_config: str) -> str:
    if not raw_config:
        return ""
    return _seal(raw_config)


class PMSConnector(ABC):
    provider: str

    @abstractmethod
    def fetch_reservations(self, cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
        raise NotImplementedError


class CloudbedsSimulator(PMSConnector):
    provider = "Cloudbeds"

    def fetch_reservations(self, cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
        # Deterministic sample set keyed by cursor generation
        gen = int(cursor or "0") + 1
        rows = [
            {
                "external_id": f"CB-{gen}-A",
                "guest_name": f"Sync Guest {gen}A",
                "email": f"sync{gen}a@example.com",
                "country": "Japan",
                "language": "en",
                "travel_type": "leisure",
                "check_in": (date.today() + timedelta(days=5)).isoformat(),
                "check_out": (date.today() + timedelta(days=8)).isoformat(),
                "amount": 460.0,
                "room_type": "Deluxe Double",
                "children": 0,
            },
            {
                "external_id": f"CB-{gen}-B",
                "guest_name": f"Sync Guest {gen}B",
                "email": f"sync{gen}b@example.com",
                "country": "Spain",
                "language": "es",
                "travel_type": "family",
                "check_in": (date.today() + timedelta(days=1)).isoformat(),
                "check_out": (date.today() + timedelta(days=4)).isoformat(),
                "amount": 620.0,
                "room_type": "Family Suite",
                "children": 2,
            },
        ]
        return rows, str(gen)


CONNECTORS: dict[str, PMSConnector] = {
    "Cloudbeds": CloudbedsSimulator(),
}


def sync_connector(db: Session, tenant_id: str, provider: str = "Cloudbeds") -> dict[str, Any]:
    """Delegate Cloudbeds to the production PMS sync path (mock or live)."""
    if provider == "Cloudbeds":
        from app.services.pms_sync import sync_cloudbeds

        return sync_cloudbeds(db, tenant_id)

    connector = (
        db.query(Connector)
        .filter(Connector.tenant_id == tenant_id, Connector.provider == provider)
        .first()
    )
    if not connector:
        raise ValueError(f"Connector {provider} not configured")

    adapter = CONNECTORS.get(provider)
    if not adapter:
        raise ValueError(f"No adapter for {provider}")

    prop = db.query(Property).filter(Property.tenant_id == tenant_id).first()
    if not prop:
        raise ValueError("No property configured")

    rows, new_cursor = adapter.fetch_reservations(connector.sync_cursor)
    imported = 0
    events = 0
    for row in rows:
        existing = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.source == provider,
                Reservation.external_id == row["external_id"],
            )
            .first()
        )
        if existing:
            continue

        guest = None
        if row.get("email"):
            guest = (
                db.query(Guest)
                .filter(Guest.tenant_id == tenant_id, Guest.email == row["email"])
                .first()
            )
        if not guest:
            guest = Guest(
                tenant_id=tenant_id,
                property_id=prop.id,
                name=row["guest_name"],
                email=row.get("email"),
                country=row.get("country"),
                language=row.get("language", "en"),
                travel_type=row.get("travel_type", "leisure"),
                children=int(row.get("children") or 0),
                communication_preference="whatsapp",
                stay_count=1,
                lifetime_spend=float(row.get("amount") or 0),
                average_booking=float(row.get("amount") or 0),
                ltv_score=58,
                satisfaction_score=70,
            )
            db.add(guest)
            db.flush()

        res = Reservation(
            tenant_id=tenant_id,
            property_id=prop.id,
            guest_id=guest.id,
            external_id=row["external_id"],
            source=provider,
            status=ReservationStatus.confirmed,
            room_type=row.get("room_type", "Deluxe Double"),
            check_in=date.fromisoformat(row["check_in"]),
            check_out=date.fromisoformat(row["check_out"]),
            total_amount=float(row.get("amount") or 0),
            currency="EUR",
            children=int(row.get("children") or 0),
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
            },
            source=provider.lower(),
            idempotency_key=f"ReservationCreated:{provider}:{row['external_id']}",
        )
        imported += 1
        events += 1

    connector.sync_cursor = new_cursor
    connector.last_sync_at = datetime.utcnow()
    connector.status = "connected"
    connector.last_error = None
    db.flush()
    return {"imported": imported, "events_emitted": events, "cursor": new_cursor}
