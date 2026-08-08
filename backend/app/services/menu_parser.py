"""Menu extraction glue: raw AI/heuristic output -> reviewable
`MenuExtractedItem`s. Confidence never reaches a hotel — this module is
the one place that turns the AI Parser's internal confidence score,
plus one hard requirement (a valid name and price), into the only two
states a user ever sees: Ready to Import / Needs Review. Mirrors
`pdf_parser.py`'s own role for reservations exactly.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.schemas import MenuExtractedItem, MenuExtractionIssue, MenuItemDraft, MenuValidationReport


def _build_item(raw: dict[str, Any]) -> tuple[MenuItemDraft | None, list[MenuExtractionIssue]]:
    """Map one AI/heuristic-extracted dict onto `MenuItemDraft`. Returns
    (None, issues) when a name or a price is missing — never a guessed
    price, which would be worse than asking a human to fill it in.
    """
    issues: list[MenuExtractionIssue] = []

    name = (raw.get("name") or "").strip()
    if not name:
        issues.append(MenuExtractionIssue(field="name", message="Could not find an item name"))
        return None, issues

    if raw.get("price") is None:
        issues.append(
            MenuExtractionIssue(field="price", message="Could not find a price for this item")
        )
        return None, issues

    payload = {
        "menu_name": (raw.get("menu_name") or "Menu").strip(),
        "name": name,
        "category": (raw.get("category") or None),
        "description": (raw.get("description") or None),
        "price": raw.get("price"),
        "currency": (raw.get("currency") or "EUR").strip().upper(),
        "available": True,
        "vegetarian": bool(raw.get("vegetarian")),
        "vegan": bool(raw.get("vegan")),
        "gluten_free": bool(raw.get("gluten_free")),
        "spicy": bool(raw.get("spicy")),
    }
    try:
        item = MenuItemDraft.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            issues.append(
                MenuExtractionIssue(
                    field=str(err["loc"][-1]) if err.get("loc") else None,
                    message=err["msg"],
                )
            )
        return None, issues
    return item, issues


def classify_extracted_items(
    raw_items: list[dict[str, Any]], *, full_text: str
) -> list[MenuExtractedItem]:
    """Convert every AI/heuristic-extracted dict into a
    `MenuExtractedItem`, gated to Ready to Import only when: the item
    validated (name + price present) and confidence clears
    `settings.pdf_confidence_threshold` (the same knob PDF import
    already uses — this is a generic "how sure was the extraction"
    threshold, not something menu-specific enough to need its own
    setting). Either failing routes the row to Needs Review — never
    partial credit.
    """
    rows: list[MenuExtractedItem] = []
    for index, raw in enumerate(raw_items):
        item, issues = _build_item(raw)
        confidence = float(raw.get("confidence") or 0.0)

        if item is not None and confidence < settings.pdf_confidence_threshold:
            issues.append(
                MenuExtractionIssue(
                    field=None, message="Extraction confidence below the review threshold"
                )
            )

        ready = item is not None and confidence >= settings.pdf_confidence_threshold
        rows.append(
            MenuExtractedItem(
                row_index=index,
                review_state="ready_to_import" if ready else "needs_review",
                item=item,
                issues=issues,
                raw_text_excerpt=full_text[:1500] if item is None else None,
            )
        )
    return rows


def build_validation_report(filename: str, rows: list[MenuExtractedItem]) -> MenuValidationReport:
    ready_count = sum(1 for row in rows if row.review_state == "ready_to_import")
    return MenuValidationReport(
        filename=filename,
        total_items=len(rows),
        ready_count=ready_count,
        needs_review_count=len(rows) - ready_count,
        rows=rows,
    )
