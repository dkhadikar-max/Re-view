"""AI Parser for PDF booking confirmations — reuses the same
structured-JSON-only, Pydantic-validated, mock/heuristic-fallback contract
as app/integrations/openai_gateway.py (PDF_IMPORT.md §8). No new provider
wiring: same `settings.openai_api_key` / `settings.openai_model`.

Confidence produced here is internal only. It never reaches a hotel —
app/services/pdf_parser.py is the one place that converts it into
Ready to Import / Needs Review (PDF_IMPORT.md §4).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You extract hotel booking reservations from the text of a
booking confirmation PDF (Booking.com, Airbnb, Expedia, a hotel's own direct
confirmation, or a travel agent booking). Return ONLY valid JSON:
{
  "reservations": [
    {
      "guest_name": "string or null",
      "guest_email": "string or null",
      "guest_phone": "string or null",
      "country": "string or null",
      "check_in": "YYYY-MM-DD or null",
      "check_out": "YYYY-MM-DD or null",
      "adults": integer or null,
      "children": integer or null,
      "room_type": "string or null",
      "total_amount": number or null,
      "currency": "3-letter code or null",
      "special_requests": "string or null",
      "confirmation_number": "string or null",
      "confidence": 0.0-1.0
    }
  ]
}
One object per reservation found in the document — most confirmations have
exactly one; a group booking may have several. If a field is not present
in the text, use null rather than guessing. `confidence` reflects how
certain you are the whole object is correct and complete, not just
whether the JSON itself parsed. Never invent a confirmation_number — if
you can't find one, return null for it.
"""


class PdfAIParser:
    """Extraction gateway: raw PDF text -> candidate reservation dicts with
    a confidence score each. Falls back to a deterministic heuristic
    extractor (below) when no API key is configured or the API call
    fails — the same "never fail the whole upload" contract §8 requires."""

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
                    # Cap input to keep cost bounded — booking confirmations
                    # are short; this comfortably covers even a multi-page
                    # group booking.
                    {"role": "user", "content": text[:12000]},
                ],
                temperature=0.0,
            )
            content = response.choices[0].message.content or "{}"
            raw = json.loads(content)
            reservations = raw.get("reservations")
            if not isinstance(reservations, list):
                raise ValueError("AI response missing a 'reservations' list")
            return reservations
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "PDF AI parser failed; falling back to heuristic extraction: %s", exc
            )
            return _heuristic_extract(text)


# --- Heuristic fallback -----------------------------------------------
# Deterministic, zero-cost, regex-based extraction — the same "$0 first"
# philosophy as zero_cost_agent.py, applied to the one path that has no
# LLM available (no API key configured, i.e. `use_mock_ai`/dev/CI). This
# is honestly imperfect: a field that can't be found with a real regex
# match is left null rather than guessed, which naturally routes
# ambiguous PDFs to Needs Review instead of importing something wrong.

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_AMOUNT_RE = re.compile(
    r"(?:total|amount|price)[^\d\n]{0,12}([A-Z]{3})?\s*[\$€£]?\s*([\d,]+\.\d{2}|\d+)",
    re.IGNORECASE,
)
_DATE_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_CONFIRMATION_RE = re.compile(
    r"(?:confirmation\s*(?:number|code|#)?|booking\s*(?:number|reference)?)[:\s#]*([A-Z0-9-]{4,20})",
    re.IGNORECASE,
)
_CHECKIN_RE = re.compile(r"check[- ]?in[:\s]*([A-Za-z0-9,\s]{6,25})", re.IGNORECASE)
_CHECKOUT_RE = re.compile(r"check[- ]?out[:\s]*([A-Za-z0-9,\s]{6,25})", re.IGNORECASE)
_NAME_RE = re.compile(
    r"(?:guest\s*name|guest|name)[:\s]*([A-Za-z][A-Za-z .'\-]{2,60})", re.IGNORECASE
)


def _parse_date_fragment(fragment: str) -> Optional[str]:
    """Best-effort parse of a short date fragment into YYYY-MM-DD, else
    None. Uses python-dateutil (already a dependency) rather than adding
    a date-parsing library just for this."""
    from dateutil import parser as dateutil_parser

    fragment = fragment.strip().splitlines()[0].strip(" ,")
    if not fragment:
        return None
    try:
        parsed = dateutil_parser.parse(fragment, fuzzy=True, dayfirst=False)
    except (ValueError, OverflowError, TypeError):
        return None
    return parsed.date().isoformat()


def _heuristic_extract(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []

    email_match = _EMAIL_RE.search(text)
    phone_match = _PHONE_RE.search(text)
    confirmation_match = _CONFIRMATION_RE.search(text)
    name_match = _NAME_RE.search(text)
    amount_match = _AMOUNT_RE.search(text)

    check_in: Optional[str] = None
    check_out: Optional[str] = None
    checkin_match = _CHECKIN_RE.search(text)
    checkout_match = _CHECKOUT_RE.search(text)
    if checkin_match:
        check_in = _parse_date_fragment(checkin_match.group(1))
    if checkout_match:
        check_out = _parse_date_fragment(checkout_match.group(1))
    if not (check_in and check_out):
        iso_dates = _DATE_ISO_RE.findall(text)
        if len(iso_dates) >= 2:
            check_in = check_in or iso_dates[0]
            check_out = check_out or iso_dates[1]

    # A plain count of how many of the 5 key signals were found with a
    # real regex match — not a model score, just a countable proxy so the
    # same Ready/Needs Review gate (§4) still applies without an LLM.
    signals = [email_match, name_match, check_in, check_out, confirmation_match]
    confidence = sum(1 for s in signals if s) / len(signals)

    return [
        {
            "guest_name": name_match.group(1).strip() if name_match else None,
            "guest_email": email_match.group(0) if email_match else None,
            "guest_phone": phone_match.group(0).strip() if phone_match else None,
            "country": None,
            "check_in": check_in,
            "check_out": check_out,
            "adults": None,
            "children": None,
            "room_type": None,
            "total_amount": (
                float(amount_match.group(2).replace(",", "")) if amount_match else None
            ),
            "currency": amount_match.group(1) if amount_match and amount_match.group(1) else None,
            "special_requests": None,
            "confirmation_number": (
                confirmation_match.group(1).strip() if confirmation_match else None
            ),
            "confidence": confidence,
        }
    ]


pdf_ai_parser = PdfAIParser()
