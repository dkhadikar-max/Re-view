"""MenuImporter — an `Importer` Protocol implementation
(app/services/importer.py), the second after `PdfImporter`. See
MENU_ORDERING.md §3 for the full design; this file wires together
pdf_extractor (text, reused unmodified) -> menu_ai_parser (AI/heuristic
extraction) -> menu_parser (Ready/Needs Review classification) and,
once a human has reviewed, creates `MenuItem` rows directly (no
Import Orchestrator reuse needed — that orchestrates Guest/Reservation
creation and Automation Engine events, neither of which a menu upload
triggers).

PDF only for v1 (frozen decision) — Excel/CSV follows only if a pilot
hotel actually needs it, not built speculatively.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.menu_ai_parser import menu_ai_parser
from app.integrations.pdf_extractor import extract_pdf_text
from app.models.entities import ImportSession, MenuItem
from app.schemas import MenuConfirmItem, MenuValidationReport
from app.services.menu_parser import build_validation_report, classify_extracted_items


class MenuImporter:
    """Implements Importer (validate/preview/import_/summary).

    `preview()` returns the same report as `validate()` — same
    reasoning as `PdfImporter`: the Extracted Item card *is* the
    preview shown to a human, there's no separate raw-row view.
    """

    def validate(self, raw_input: bytes, *, filename: str) -> MenuValidationReport:
        text = extract_pdf_text(raw_input)

        if not text.strip():
            return build_validation_report(filename, [])

        raw_items = menu_ai_parser.extract(text)
        rows = classify_extracted_items(raw_items, full_text=text)
        return build_validation_report(filename, rows)

    def preview(self, raw_input: bytes, *, filename: str) -> MenuValidationReport:
        return self.validate(raw_input, filename=filename)

    def import_(
        self,
        raw_input: list[MenuConfirmItem],
        session: ImportSession,
        *,
        db: Session,
        tenant_id: str,
        property_id: str,
    ) -> dict[str, Any]:
        """Writes approved (optionally edited) rows as `MenuItem` rows.
        No dedup against existing items — a re-upload of a revised menu
        always creates fresh rows rather than guessing which existing
        item a re-extracted one corresponds to (fuzzy name-matching
        across an edited menu is exactly the kind of guess this
        codebase avoids elsewhere). Staff manage superseded items by
        marking them unavailable or editing them directly via the menu
        editor endpoint; a "replace this upload's items" convenience is
        a reasonable future addition once a pilot hotel actually re-
        uploads a revised menu, not built speculatively here.
        """
        imported: list[MenuItem] = []
        for row in raw_input:
            item = MenuItem(
                tenant_id=tenant_id,
                property_id=property_id,
                menu_name=row.item.menu_name,
                name=row.item.name,
                category=row.item.category,
                description=row.item.description,
                price=row.item.price,
                currency=row.item.currency,
                available=row.item.available,
                vegetarian=row.item.vegetarian,
                vegan=row.item.vegan,
                gluten_free=row.item.gluten_free,
                spicy=row.item.spicy,
                source_import_id=session.id,
            )
            db.add(item)
            imported.append(item)
            session.rows_imported += 1
        db.flush()
        return {"imported": imported}

    def summary(self, session: ImportSession, *, db: Session) -> dict[str, Any]:
        """Menu's own summary, not `build_import_summary` (that queries
        `Reservation.import_session_id` — a menu upload never creates
        one). The "so what" number here is simply how many items this
        upload published, grouped by menu.
        """
        items = (
            db.query(MenuItem).filter(MenuItem.source_import_id == session.id).all()
        )
        by_menu: dict[str, int] = {}
        for item in items:
            by_menu[item.menu_name] = by_menu.get(item.menu_name, 0) + 1
        return {"items_imported": len(items), "by_menu": by_menu}


menu_importer = MenuImporter()
