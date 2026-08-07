"""PDF extraction glue: raw AI/heuristic output -> reviewable
`PdfExtractedRow`s. Confidence never reaches a hotel (PDF_IMPORT.md §4) —
this module is the one place that turns the AI Parser's internal
confidence score, plus a couple of hard requirements, into the only two
states a user ever sees: Ready to Import / Needs Review.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from pydantic import ValidationError

from app.core.config import settings
from app.schemas import (
    PdfExtractedRow,
    PdfExtractionIssue,
    PdfValidationReport,
    ReservationCreate,
)


def confirmation_external_id(confirmation_number: str) -> str:
    """Deterministic external_id from a confirmation/booking/itinerary
    number (PDF_IMPORT.md §11.1) so re-uploading the same document is
    idempotent, not just deduplicated by luck the way CSV's random UUID
    is. Truncation isn't needed — Reservation.external_id is String(128)
    and a "PDF-" prefix + sha256 hex digest is 68 chars.
    """
    normalized = confirmation_number.strip().lower()
    digest = hashlib.sha256(f"pdf:{normalized}".encode()).hexdigest()
    return f"PDF-{digest}"


def fallback_external_id(reservation: ReservationCreate) -> str:
    """Fallback identity when no confirmation/booking/itinerary number
    was found at all (§11.1's original decision was "Needs Review rather
    than a random ID" — this refines that, per review feedback on this
    PR: a *random* ID was rejected because it makes idempotency
    impossible, but a hash of the reservation's own normalized fields is
    still deterministic, not random. Re-uploading the same unidentified
    PDF still collapses to the same external_id; it's just less precise
    than a real confirmation number at telling apart two genuinely
    different bookings for the same guest on the same dates — an
    accepted, documented tradeoff for the rare document that has no
    printed reference at all.
    """
    normalized = "|".join(
        [
            (reservation.guest_name or "").strip().lower(),
            (reservation.guest_email or "").strip().lower(),
            reservation.check_in.isoformat(),
            reservation.check_out.isoformat(),
            f"{reservation.total_amount:.2f}",
        ]
    )
    digest = hashlib.sha256(f"pdf-fallback:{normalized}".encode()).hexdigest()
    return f"PDFX-{digest}"


def resolve_external_id(
    confirmation_number: Optional[str], reservation: ReservationCreate
) -> str:
    """The one place both identity strategies meet: prefer the real
    confirmation number when the reviewer provided one, otherwise fall
    back to the content hash rather than refusing to import at all."""
    if confirmation_number and confirmation_number.strip():
        return confirmation_external_id(confirmation_number)
    return fallback_external_id(reservation)


def _build_reservation(
    raw: dict[str, Any],
) -> tuple[Optional[ReservationCreate], list[PdfExtractionIssue]]:
    """Map one AI/heuristic-extracted dict onto ReservationCreate — the
    exact same schema CSV and manual entry produce (PDF_IMPORT.md §5).
    Returns (None, issues) when required fields (dates) are missing
    rather than guessing a date, which would be worse than asking a
    human to fill it in via Manual Entry.
    """
    issues: list[PdfExtractionIssue] = []

    if not raw.get("check_in") or not raw.get("check_out"):
        issues.append(
            PdfExtractionIssue(
                field="check_in/check_out",
                message="Could not find both a check-in and check-out date in the document",
            )
        )
        return None, issues

    payload = {
        "guest_name": (raw.get("guest_name") or "").strip() or "Unknown Guest",
        "guest_email": raw.get("guest_email") or None,
        "guest_phone": raw.get("guest_phone") or None,
        "country": raw.get("country") or None,
        "language": "en",
        "travel_type": "leisure",
        "source": "pdf",
        "room_type": (raw.get("room_type") or "Standard").strip(),
        "check_in": raw.get("check_in"),
        "check_out": raw.get("check_out"),
        "adults": raw.get("adults") or 2,
        "children": raw.get("children") or 0,
        "total_amount": raw.get("total_amount") or 0,
        "currency": (raw.get("currency") or "EUR").strip().upper(),
        "special_requests": raw.get("special_requests") or None,
        "communication_preference": "email",
    }
    if not raw.get("guest_email"):
        issues.append(
            PdfExtractionIssue(
                field="guest_email",
                message="No email found — this guest can't be matched on repeat visits",
            )
        )

    try:
        reservation = ReservationCreate.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            issues.append(
                PdfExtractionIssue(
                    field=str(err["loc"][-1]) if err.get("loc") else None,
                    message=err["msg"],
                )
            )
        return None, issues
    return reservation, issues


def classify_extracted_reservations(
    raw_reservations: list[dict[str, Any]], *, full_text: str
) -> list[PdfExtractedRow]:
    """Convert every AI/heuristic-extracted dict into a PdfExtractedRow,
    gated to Ready to Import only when: the reservation validated, a
    confirmation number was found (needed for dedup, §11.1), and
    confidence clears `settings.pdf_confidence_threshold`. Any one of
    those failing routes the row to Needs Review — never partial credit.
    """
    rows: list[PdfExtractedRow] = []
    for index, raw in enumerate(raw_reservations):
        reservation, issues = _build_reservation(raw)
        confirmation_number = (raw.get("confirmation_number") or "").strip() or None
        confidence = float(raw.get("confidence") or 0.0)

        if not confirmation_number:
            issues.append(
                PdfExtractionIssue(
                    field="confirmation_number",
                    message=(
                        "No confirmation/booking number found — duplicate detection "
                        "will fall back to matching on guest, dates, and amount, "
                        "which is less precise. Fill it in below if you can see one "
                        "on the document."
                    ),
                )
            )
        if reservation is not None and confidence < settings.pdf_confidence_threshold:
            issues.append(
                PdfExtractionIssue(
                    field=None, message="Extraction confidence below the review threshold"
                )
            )

        ready = (
            reservation is not None
            and confirmation_number is not None
            and confidence >= settings.pdf_confidence_threshold
        )
        rows.append(
            PdfExtractedRow(
                row_index=index,
                review_state="ready_to_import" if ready else "needs_review",
                confirmation_number=confirmation_number,
                reservation=reservation,
                issues=issues,
                raw_text_excerpt=full_text[:1500] if reservation is None else None,
            )
        )
    return rows


def build_validation_report(filename: str, rows: list[PdfExtractedRow]) -> PdfValidationReport:
    ready_count = sum(1 for row in rows if row.review_state == "ready_to_import")
    return PdfValidationReport(
        filename=filename,
        total_reservations=len(rows),
        ready_count=ready_count,
        needs_review_count=len(rows) - ready_count,
        rows=rows,
    )
