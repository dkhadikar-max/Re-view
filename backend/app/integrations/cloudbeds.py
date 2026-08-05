from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.integrations.base import NormalizedGuest, NormalizedReservation

logger = logging.getLogger(__name__)


class CloudbedsClient:
    """Cloudbeds PMS integration — Priority 1 for production.

    Auth modes:
    1. Property API key (`CLOUDBEDS_API_KEY`) — simplest for first hotel
    2. OAuth2 (`CLOUDBEDS_CLIENT_ID` + secret) — multi-property

    Endpoints used (v1.2):
    - getReservations / getReservation
    - getGuest
    - putReservation (status transitions for check-in/out where supported)
    """

    provider = "Cloudbeds"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        property_id: Optional[str] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.cloudbeds_api_key
        self.access_token = access_token
        self.property_id = property_id or settings.cloudbeds_property_id
        self.base_url = settings.cloudbeds_base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key or self.access_token)

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def _headers(self) -> dict[str, str]:
        if self.access_token:
            return {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            }
        if self.api_key:
            return {
                "Authorization": f"Bearer {self.api_key}",
                "x-api-key": self.api_key,
                "Accept": "application/json",
            }
        return {"Accept": "application/json"}

    def oauth_authorize_url(self, state: str) -> str:
        params = {
            "client_id": settings.cloudbeds_client_id,
            "redirect_uri": settings.cloudbeds_redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{settings.cloudbeds_auth_url}/oauth?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        if not settings.cloudbeds_client_id or not settings.cloudbeds_client_secret:
            raise RuntimeError("Cloudbeds OAuth client credentials not configured")
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.cloudbeds_auth_url}/access_token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.cloudbeds_client_id,
                    "client_secret": settings.cloudbeds_client_secret,
                    "redirect_uri": settings.cloudbeds_redirect_uri,
                    "code": code,
                },
            )
            resp.raise_for_status()
            return resp.json()

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.cloudbeds_auth_url}/access_token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.cloudbeds_client_id,
                    "client_secret": settings.cloudbeds_client_secret,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            return resp.json()

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        params = dict(params or {})
        if self.property_id and "propertyID" not in params:
            params["propertyID"] = self.property_id
        with httpx.Client(timeout=45.0, headers=self._headers()) as client:
            resp = client.get(f"{self.base_url}/{path.lstrip('/')}", params=params)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(data)
        if self.property_id and "propertyID" not in payload:
            payload["propertyID"] = self.property_id
        with httpx.Client(timeout=45.0, headers=self._headers()) as client:
            resp = client.post(f"{self.base_url}/{path.lstrip('/')}", data=payload)
            resp.raise_for_status()
            return resp.json()

    def fetch_reservations(
        self, *, cursor: Optional[str] = None
    ) -> tuple[list[NormalizedReservation], Optional[str]]:
        if not self.configured:
            return self._mock_fetch(cursor)

        params: dict[str, Any] = {"pageSize": 50}
        if cursor:
            params["pageNumber"] = int(cursor)
        else:
            params["pageNumber"] = 1

        data = self._get("getReservations", params)
        rows = data.get("data") or data.get("reservations") or []
        if isinstance(rows, dict):
            rows = list(rows.values())

        normalized = [self._normalize_reservation(r) for r in rows]
        page = int(params["pageNumber"])
        next_cursor = str(page + 1) if len(normalized) >= 50 else None
        return normalized, next_cursor

    def fetch_guest(self, guest_id: str) -> NormalizedGuest:
        if not self.configured:
            return NormalizedGuest(external_id=guest_id, name="Mock Guest")
        data = self._get("getGuest", {"guestID": guest_id})
        g = data.get("data") or data
        return NormalizedGuest(
            external_id=str(g.get("guestID") or guest_id),
            name=f"{g.get('firstName', '')} {g.get('lastName', '')}".strip() or "Guest",
            email=g.get("email"),
            phone=g.get("phone") or g.get("cellPhone"),
            country=g.get("country") or g.get("countryName"),
            language=(g.get("preferredLanguage") or "en")[:8],
        )

    def check_in(self, external_id: str) -> dict[str, Any]:
        if not self.configured:
            return {"ok": True, "mode": "mock", "external_id": external_id, "status": "checked_in"}
        # Cloudbeds uses putReservation / postReservation assignment flows; status update:
        return self._post(
            "putReservation",
            {"reservationID": external_id, "status": "checked_in"},
        )

    def check_out(self, external_id: str) -> dict[str, Any]:
        if not self.configured:
            return {"ok": True, "mode": "mock", "external_id": external_id, "status": "checked_out"}
        return self._post(
            "putReservation",
            {"reservationID": external_id, "status": "checked_out"},
        )

    def _normalize_reservation(self, raw: dict[str, Any]) -> NormalizedReservation:
        guest_name = (
            raw.get("guestName")
            or f"{raw.get('guestFirstName', '')} {raw.get('guestLastName', '')}".strip()
            or "Guest"
        )
        status_raw = str(raw.get("status") or raw.get("reservationStatus") or "confirmed").lower()
        status_map = {
            "confirmed": "confirmed",
            "not_confirmed": "confirmed",
            "checked_in": "checked_in",
            "checkedin": "checked_in",
            "in_house": "checked_in",
            "checked_out": "checked_out",
            "checkedout": "checked_out",
            "canceled": "cancelled",
            "cancelled": "cancelled",
        }
        check_in = self._parse_date(raw.get("startDate") or raw.get("checkIn") or raw.get("arrivalDate"))
        check_out = self._parse_date(raw.get("endDate") or raw.get("checkOut") or raw.get("departureDate"))
        return NormalizedReservation(
            external_id=str(raw.get("reservationID") or raw.get("reservation_id") or raw.get("id")),
            source="Cloudbeds",
            guest=NormalizedGuest(
                external_id=str(raw.get("guestID") or raw.get("guest_id") or "") or None,
                name=guest_name,
                email=raw.get("guestEmail") or raw.get("email"),
                phone=raw.get("guestPhone") or raw.get("phone"),
                country=raw.get("guestCountry") or raw.get("country"),
                language=str(raw.get("preferredLanguage") or "en")[:8],
                children=int(raw.get("children") or 0),
            ),
            status=status_map.get(status_raw, "confirmed"),
            room_type=str(raw.get("roomTypeName") or raw.get("roomType") or "Standard"),
            check_in=check_in,
            check_out=check_out,
            adults=int(raw.get("adults") or 2),
            children=int(raw.get("children") or 0),
            total_amount=float(raw.get("balance") or raw.get("total") or raw.get("grandTotal") or 0),
            currency=str(raw.get("currency") or "EUR"),
            special_requests=raw.get("specialRequests") or raw.get("notes"),
            raw=raw,
        )

    @staticmethod
    def _parse_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if not value:
            return date.today()
        text = str(value)[:10]
        return date.fromisoformat(text)

    def _mock_fetch(
        self, cursor: Optional[str]
    ) -> tuple[list[NormalizedReservation], Optional[str]]:
        gen = int(cursor or "0") + 1
        from datetime import timedelta

        rows = [
            NormalizedReservation(
                external_id=f"CB-MOCK-{gen}-A",
                source="Cloudbeds",
                guest=NormalizedGuest(
                    external_id=f"G-{gen}-A",
                    name=["Yuki Tanaka", "Amelia Chen", "Sofia Ricci", "Noah Berg"][
                        (gen - 1) % 4
                    ],
                    email=f"guest{gen}a@example.com",
                    country="Japan",
                    language="en",
                ),
                status="confirmed",
                room_type="Deluxe Double",
                check_in=date.today() + timedelta(days=5),
                check_out=date.today() + timedelta(days=8),
                total_amount=460,
            ),
            NormalizedReservation(
                external_id=f"CB-MOCK-{gen}-B",
                source="Cloudbeds",
                guest=NormalizedGuest(
                    external_id=f"G-{gen}-B",
                    name=["Elena Vargas", "Luca Moretti", "Priya Sharma", "Jonas Lind"][
                        (gen - 1) % 4
                    ],
                    email=f"guest{gen}b@example.com",
                    country="Spain",
                    language="es",
                    children=2,
                ),
                status="confirmed",
                room_type="Family Suite",
                check_in=date.today() + timedelta(days=1),
                check_out=date.today() + timedelta(days=4),
                total_amount=620,
                children=2,
            ),
        ]
        return rows, str(gen)


cloudbeds_client = CloudbedsClient()
