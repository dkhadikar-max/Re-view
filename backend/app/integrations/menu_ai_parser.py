"""AI Parser for hotel menu PDFs — MENU_ORDERING.md §3.2, reuses the
same structured-JSON-only, mock/heuristic-fallback contract as
`pdf_ai_parser.py` (booking confirmations) and
`app/integrations/openai_gateway.py` more broadly. No new provider
wiring: same `settings.openai_api_key` / `settings.openai_model`.

Confidence produced here is internal only — `app/services/menu_parser.py`
is the one place that turns it into Ready to Import / Needs Review,
same separation `pdf_parser.py` already established.

Unlike a booking confirmation (typically one reservation per document),
a menu PDF typically has many items — this extracts a list, not a
single object.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You extract menu items from the text of a hotel menu PDF
(breakfast menu, room service menu, bar menu, restaurant menu, etc.).
Return ONLY valid JSON:
{
  "items": [
    {
      "menu_name": "string or null (e.g. 'Breakfast Menu', 'Room Service Menu' — the section or document this item belongs to)",
      "name": "string or null",
      "category": "string or null (e.g. 'Starter', 'Main Course', 'Dessert', 'Beverage')",
      "description": "string or null",
      "price": number or null,
      "currency": "3-letter code or null",
      "vegetarian": true or false,
      "vegan": true or false,
      "gluten_free": true or false,
      "spicy": true or false,
      "confidence": 0.0-1.0
    }
  ]
}
One object per distinct dish or drink found in the document. If a field is
not present or not clearly stated in the text, use null (or false for the
dietary booleans) rather than guessing. `confidence` reflects how certain
you are the whole object is correct and complete, not just whether the
JSON itself parsed. Never invent a price — if you can't find one for an
item, return null for it.
"""


class MenuAIParser:
    """Extraction gateway: raw menu PDF text -> candidate menu item dicts
    with a confidence score each. Falls back to a deterministic
    heuristic extractor (below) when no API key is configured or the
    API call fails — the same "never fail the whole upload" contract
    `pdf_ai_parser.py` already follows."""

    def __init__(self) -> None:
        self.model = settings.openai_model
        self.api_key = settings.openai_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and not settings.use_mock_ai

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def extract(self, text: str) -> list[dict[str, Any]]:
        if not self.configured:
            return _heuristic_extract(text)

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    # A menu can run long (multi-page room service +
                    # bar + breakfast in one PDF) — cap input the same
                    # way pdf_ai_parser.py does to keep cost bounded.
                    {"role": "user", "content": text[:12000]},
                ],
                temperature=0.0,
            )
            content = response.choices[0].message.content or "{}"
            raw = json.loads(content)
            items = raw.get("items")
            if not isinstance(items, list):
                raise ValueError("AI response missing an 'items' list")
            return items
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Menu AI parser failed; falling back to heuristic extraction: %s", exc
            )
            return _heuristic_extract(text)


# --- Heuristic fallback -----------------------------------------------
# Deterministic, zero-cost, line-based extraction for when no LLM is
# available (no API key, i.e. mock/dev/CI) — same "$0 first" philosophy
# as pdf_ai_parser.py's own heuristic. Menu layouts vary far more than
# booking confirmations do, so this is honestly conservative: it only
# ever extracts a name and a price from a line that clearly has both,
# in that order, and leaves category/description/dietary tags entirely
# unset (never guessed) — everything else lands in Needs Review rather
# than a wrong dish being invented from a garbled line.

_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
_CURRENCY_CODES = "EUR|USD|GBP"

# "<name> <dots/dashes/spaces leader> <optional currency> <amount>" —
# covers the most common menu layouts: dot leaders ("Grilled Salmon
# .......... 24.00"), a wide gap before a right-aligned price
# ("Grilled Salmon      24.00"), or a currency symbol/code directly
# before the number ("Grilled Salmon  €24.00" / "Grilled Salmon 24.00
# EUR"). Requires at least two spaces or a run of dots/dashes as the
# leader so a mid-sentence number (a phone number, an address) doesn't
# get misread as a price.
_ITEM_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9()'&,.\- ]{1,80}?)"
    # The leader is dots/dashes/spaces in any mix (dot-leader menus often
    # end in a trailing space before the price, e.g. "..........  24.00"
    # or "..........  €18.00") — a currency symbol immediately precedes
    # the amount, wherever the leader itself ends.
    r"(?:[.\-\s]{2,})"
    r"(?P<currency_pre>[€$£])?"
    r"(?P<amount>\d+[.,]\d{2})\s*"
    r"(?P<currency_post>[A-Z]{3})?\s*$"
)


def _heuristic_extract(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []

    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _ITEM_LINE_RE.match(line)
        if not match:
            continue

        name = match.group("name").strip(" .-")
        if not name:
            continue
        amount = float(match.group("amount").replace(",", "."))
        currency = None
        if match.group("currency_pre"):
            currency = _CURRENCY_SYMBOLS.get(match.group("currency_pre"))
        elif match.group("currency_post"):
            currency = match.group("currency_post").upper()

        # A clean match on both name and price is the only signal this
        # heuristic has — no partial credit, same as pdf_ai_parser.py's
        # per-field confidence proxy, just simpler since there are only
        # two fields to have found at all.
        items.append(
            {
                "menu_name": None,
                "name": name,
                "category": None,
                "description": None,
                "price": amount,
                "currency": currency,
                "vegetarian": False,
                "vegan": False,
                "gluten_free": False,
                "spicy": False,
                "confidence": 0.8 if currency else 0.7,
            }
        )
    return items


menu_ai_parser = MenuAIParser()
