"""The shared `Importer` interface — see PDF_IMPORT.md §9.

Formalizes what CSV and manual entry already do implicitly, so PDF, email,
and future PMS connectors don't each reinvent it:

    validate() -> a report a human can read before anything is written
    preview()  -> the rows a review screen renders
    import_()  -> writes through the same Import Orchestrator every
                  source already uses (import_reservation / ImportSession)
    summary()  -> the "so what" numbers, already shared via
                  build_import_summary()

`PdfImporter` (app/services/pdf_importer.py) is the first and, for now,
only formal implementation of this Protocol. CSV's existing functions
(`_validate_csv_rows`, `_read_csv_rows` in app/api/routes.py) already do
the same job in spirit but are intentionally NOT being refactored into
this shape yet — repackaging already-shipped, CI-verified code without
being able to run the test suite live (see CLAUDE.md, Python 3.14 sandbox
limitation) is a risk not worth taking in the same change that ships new
functionality. Tracked as its own follow-up (task #37 stays open for
that half; this file only closes the "define the interface" half).

The return types are intentionally left loose (`Any`) rather than forced
into one shared Pydantic model: CSV's report shape (`CsvValidationReport`)
and PDF's (`PdfValidationReport`) differ in real, meaningful ways (PDF
rows carry a review state and an editable draft, CSV rows carry a line
number), and forcing a shared shape now — before a second and third
importer exist to triangulate against — would be exactly the kind of
premature abstraction CLAUDE.md warns against. What's shared is the
*sequence*, not yet the exact payload; that's what this Protocol pins
down.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.models.entities import ImportSession


@runtime_checkable
class Importer(Protocol):
    """One import source's contract: validate, preview, import, summarize."""

    def validate(self, raw_input: Any) -> Any:
        """Read-only. Parses `raw_input` and reports what would happen —
        never writes to the database, never creates an ImportSession."""
        ...

    def preview(self, raw_input: Any) -> Any:
        """Returns exactly what the review screen renders for a human to
        approve/edit before import — for CSV this is the raw valid rows,
        for PDF this is the Extracted Reservation cards (PDF_IMPORT.md §7)."""
        ...

    def import_(self, raw_input: Any, session: ImportSession) -> Any:
        """Writes the approved rows through the Import Orchestrator
        (`import_reservation`). Thin by design — orchestration, dedup, and
        automation are already shared, this method should barely differ
        between importers."""
        ...

    def summary(self, session: ImportSession) -> dict[str, Any]:
        """The Import Summary numbers. Every importer gets this for free
        via `build_import_summary` — no importer should need to override
        it unless it introduces a metric no other source has."""
        ...
