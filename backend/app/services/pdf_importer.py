"""PdfImporter — the first formal implementation of the shared `Importer`
Protocol (app/services/importer.py). See PDF_IMPORT.md for the full design;
this file wires together pdf_extractor (text) -> pdf_ai_parser (AI/heuristic
extraction) -> pdf_parser (Ready/Needs Review classification) and, once a
human has reviewed, the same Import Orchestrator every other source uses.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.pdf_ai_parser import pdf_ai_parser
from app.integrations.pdf_extractor import extract_pdf_text
from app.models.entities import ImportSession, Reservation
from app.schemas import (
    PdfConfirmRow,
    PdfExtractedRow,
    PdfExtractionIssue,
    PdfValidationReport,
)
from app.services.import_orchestrator import build_import_summary, import_reservation
from app.services.pdf_parser import (
    build_validation_report,
    classify_extracted_reservations,
    pdf_external_id,
)


class PdfImporter:
    """Implements Importer (validate/preview/import_/summary).

    `preview()` returns the same report as `validate()` — PDF has no
    separate "raw row" preview the way CSV does; the Extracted
    Reservation card *is* the preview shown to a human (PDF_IMPORT.md §7).
    """

    def validate(self, raw_input: bytes, *, filename: str) -> PdfValidationReport:
        text = extract_pdf_text(raw_input)

        if not text.strip():
            # No digital text layer at all — the OCR fallback path is
            # explicitly out of scope for v1 (PDF_IMPORT.md §10). Route to
            # Needs Review pointing at Manual Entry rather than pretending
            # OCR exists.
            return build_validation_report(
                filename,
                [
                    PdfExtractedRow(
                        row_index=0,
                        review_state="needs_review",
                        confirmation_number=None,
                        reservation=None,
                        issues=[
                            PdfExtractionIssue(
                                field=None,
                                message=(
                                    "This PDF appears to be scanned or image-only "
                                    "— no digital text found. Use Manual Entry for "
                                    "this reservation instead."
                                ),
                            )
                        ],
                        raw_text_excerpt=None,
                    )
                ],
            )

        raw_reservations = pdf_ai_parser.extract(text)
        if not raw_reservations:
            return build_validation_report(
                filename,
                [
                    PdfExtractedRow(
                        row_index=0,
                        review_state="needs_review",
                        confirmation_number=None,
                        reservation=None,
                        issues=[
                            PdfExtractionIssue(
                                field=None,
                                message="Could not identify a reservation in this document.",
                            )
                        ],
                        raw_text_excerpt=text[:1500],
                    )
                ],
            )

        rows = classify_extracted_reservations(raw_reservations, full_text=text)
        return build_validation_report(filename, rows)

    def preview(self, raw_input: bytes, *, filename: str) -> PdfValidationReport:
        return self.validate(raw_input, filename=filename)

    def import_(
        self,
        raw_input: list[PdfConfirmRow],
        session: ImportSession,
        *,
        db: Session,
        tenant_id: str,
        property_id: str,
    ) -> dict[str, Any]:
        """Writes approved rows through the same Import Orchestrator every
        source uses. Duplicate re-uploads (same tenant/source/external_id)
        are detected up front and skipped, not raised as a 500 from the
        database's unique constraint — PDF_IMPORT.md §6's "detected via
        the existing unique constraint" is the *invariant*, not the UX;
        this pre-check makes re-uploading the same PDF a no-op instead of
        an error.
        """
        imported: list[Reservation] = []
        duplicate_confirmation_numbers: list[str] = []

        for row in raw_input:
            external_id = pdf_external_id(row.confirmation_number)
            existing = (
                db.query(Reservation)
                .filter(
                    Reservation.tenant_id == tenant_id,
                    Reservation.source == row.reservation.source,
                    Reservation.external_id == external_id,
                )
                .first()
            )
            if existing is not None:
                duplicate_confirmation_numbers.append(row.confirmation_number)
                session.rows_skipped += 1
                continue

            _guest, reservation, _created = import_reservation(
                db,
                tenant_id=tenant_id,
                property_id=property_id,
                payload=row.reservation,
                external_id=external_id,
                event_source="pdf",
                import_session=session,
            )
            imported.append(reservation)

        return {
            "imported": imported,
            "duplicate_confirmation_numbers": duplicate_confirmation_numbers,
        }

    def summary(self, session: ImportSession, *, db: Session) -> dict[str, Any]:
        return build_import_summary(db, session)


pdf_importer = PdfImporter()
