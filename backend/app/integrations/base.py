from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol


@dataclass
class NormalizedGuest:
    external_id: Optional[str]
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    language: str = "en"
    children: int = 0


@dataclass
class NormalizedReservation:
    external_id: str
    source: str
    guest: NormalizedGuest
    status: str  # confirmed | checked_in | checked_out | cancelled
    room_type: str
    check_in: date
    check_out: date
    adults: int = 2
    children: int = 0
    total_amount: float = 0.0
    currency: str = "EUR"
    special_requests: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    provider: str
    provider_message_id: str
    status: str = "sent"  # sent | queued | failed
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationStatus:
    provider: str
    configured: bool
    mode: str  # live | mock
    detail: str = ""


class MessagingAdapter(Protocol):
    name: str

    def send(self, *, to: str, body: str, subject: Optional[str] = None) -> SendResult: ...


class PMSAdapter(Protocol):
    provider: str

    def fetch_reservations(
        self, *, cursor: Optional[str] = None
    ) -> tuple[list[NormalizedReservation], Optional[str]]: ...

    def check_in(self, external_id: str) -> dict[str, Any]: ...

    def check_out(self, external_id: str) -> dict[str, Any]: ...
