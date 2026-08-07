# PDF Import — Design Document

Status: Draft, not yet implemented. No code has been written against this
document. Review and revise here first — per explicit decision, an hour of
design now is worth more than days of rework later.

---

## 1. Why this needs a design pass first

Every prior import source (manual, CSV) produced a `ReservationCreate`
deterministically — a form submit or a CSV row either parses into that
shape or it doesn't, and the rule for "doesn't" is a Pydantic validation
error. PDF import introduces a step none of those sources have: an AI
model has to *infer* a `ReservationCreate` from unstructured text, which
means it can be wrong in ways a parser never is — confidently wrong, not
just malformed. Every section below exists to contain that risk without
slowing down the common case (a normal, digital-text booking PDF).

## 2. Supported documents (v1)

| Source | Format | Notes |
|---|---|---|
| Booking.com confirmation | Digital PDF | Consistent template, high confidence expected |
| Airbnb confirmation | Digital PDF | Consistent template |
| Expedia confirmation | Digital PDF | Consistent template |
| Direct booking (hotel's own confirmation) | Digital PDF | Format varies per hotel — lower confidence expected until the hotel's own template is seen a few times |
| Travel agent booking | Digital or scanned | Least consistent format; most likely to need the OCR path and most likely to need human review regardless of confidence |

Anything else (a random attachment, a non-booking PDF) is an **error case**
(§5), not a fifth format to support.

## 3. Pipeline

Reuses the existing Import Foundation exactly as-is — PDF is a new
*Importer*, not a new destination. Everything from Validator onward is
the same `_validate_csv_row`-equivalent → `import_reservation` path CSV
already uses.

```
Upload PDF
    │
    ▼
Digital text layer present?
    │
    ├── Yes (most booking confirmations) ─────┐
    │                                          ▼
    │                                   Extract text directly
    │                                   (pdfplumber / pypdf — no OCR cost)
    │                                          │
    └── No (scanned / image-only) ─────┐       │
                                        ▼       │
                                 OCR (Tesseract or a
                                 cloud OCR API — only
                                 reached when needed)  │
                                        │              │
                                        └──────┬───────┘
                                               ▼
                                        AI Parser
                              (reuses app/integrations/openai_gateway.py's
                               pattern: structured-JSON-only, Pydantic-
                               validated, mock/heuristic fallback when no
                               API key — same contract as ai_orchestrator
                               already uses for guest messaging decisions)
                                               │
                                               ▼
                                  Normalized ReservationCreate
                              (the exact same schema CSV/manual produce —
                               PDF does not get its own shape)
                                               │
                                               ▼
                                     Validator
                              (_validate_csv_row's logic, generalized —
                               see §7, this becomes shared code)
                                               │
                                               ▼
                                   Review (mandatory — §6)
                                               │
                                               ▼
                                Import Orchestrator → Guest Service
                                → Reservation Service → Automation Engine
                              (100% unchanged from CSV/manual — this is
                               the whole point of having built it as a
                               shared pipeline)
```

**Digital-first, OCR-only-when-needed** is a hard requirement, not an
optimization to add later: OCR is slower, costs more (either compute or a
paid API), and is measurably less accurate than reading a PDF's actual
text layer. Most booking confirmations from Booking.com/Airbnb/Expedia
are digitally generated and have a text layer — OCR should be the
minority path, reached only for scanned travel-agent documents.

## 4. Confidence — never a number

Per the app's existing convention (Messages page already shows a
"Needs review" badge instead of a raw confidence percentage; Approvals
already gates on a confidence threshold without exposing the number to
the manager), PDF extraction follows the same rule. The AI Parser
produces a real confidence score internally for the *validator* to use as
a threshold, but the UI only ever shows one of two states:

| Internal state | User-facing label |
|---|---|
| Above threshold, all required fields present, no ambiguity flags | **Ready to Import** |
| Below threshold, missing required field, or an ambiguity flag fired (e.g. two possible check-in dates found in the text) | **Needs Review** |

The threshold itself is a config value (mirrors `settings.zero_cost_agent`-
style flags already in `core/config.py`), not something surfaced to the
hotel. A hotel manager should never have to decide what "82%" means.

## 5. Extraction schema

The AI Parser's job is to map free text onto exactly the fields
`ReservationCreate` already defines — no new schema, no PDF-specific
shape. Restated here grouped the way the source document is naturally
structured, for prompt-design reference:

| Group | Fields | Maps to `ReservationCreate` |
|---|---|---|
| Guest | Name, Email, Phone, Country | `guest_name`, `guest_email`, `guest_phone`, `country` |
| Stay | Arrival, Departure, Adults, Children | `check_in`, `check_out`, `adults`, `children` |
| Room | Room type | `room_type` |
| Payment | Total amount, currency | `total_amount`, `currency` |
| Special requests | Free text | `special_requests` |
| OTA / Property | Which platform, which property (for the "wrong hotel" error case, §6) | Not stored on `ReservationCreate` directly — used only to validate the PDF belongs to this tenant before parsing proceeds |

No new `ReservationCreate` fields are anticipated. If the AI Parser
can't map a field onto this existing schema, that's a validation gap to
raise, not a reason to grow the schema per-source.

## 6. Error cases (must be handled explicitly, not silently swallowed)

| Case | Handling |
|---|---|
| Unreadable/corrupt PDF | Reject at upload, same class of error as CSV's "must be UTF-8 encoded" — a clear message, no import session created |
| Password-protected PDF | Reject at upload with a specific message ("This PDF is password-protected — remove the password and re-upload") rather than a generic parse failure |
| Wrong hotel (PDF is a real booking confirmation, but for a different property) | Flag as **Needs Review**, never silently import into the wrong tenant's guest list |
| Missing required dates | **Needs Review** — same as a CSV row missing `check_in`/`check_out` today |
| Missing email | **Warning**, not an error — exactly like CSV today (a guest can still be imported without email, just can't be deduplicated by it) |
| Duplicate reservation (same PDF uploaded twice, or the reservation already exists) | Detected via the existing `Reservation` unique constraint on `(tenant_id, source, external_id)` — needs an external_id derivation strategy from the PDF's own confirmation number so re-uploads are idempotent, not just deduplicated by luck |
| Multiple reservations in one PDF (e.g. a group booking) | Parser returns a list, not a single object; each one goes through Validator/Review independently — same one-PDF-many-rows relationship CSV already has with many-rows-per-file |

None of these should ever result in a row being imported unreviewed. See §7.

## 7. Review UI — never auto-import

This is the one hard rule for PDF that CSV didn't need as strictly: CSV
rows that pass validation import automatically (per the CSV Validation
Preview work — "Continue" already means "import the valid ones"). PDF
does **not** get that shortcut, regardless of confidence:

```
Extracted Reservation (shown exactly as it will be imported)
        │
        ▼
    Approve  ──────▶  Import
        │
        ▼
      Edit  ──────▶  (corrected) ──▶ Approve ──▶ Import
```

Even a "Ready to Import" extraction is shown to a human before it writes
anything — the label describes how much scrutiny it *deserves*, not
whether it skips review. This is consistent with the rest of the
product's stance ("manager approval on every commercial action") and
specifically because AI extraction is the first import source in this
product where the source data itself can be misread, not just malformed.

## 8. AI provider, cost, and fallback

Reuses the existing `AIGateway` contract (`app/integrations/openai_gateway.py`):
structured-JSON-only, Pydantic-validated, and a deterministic fallback
when no API key is configured (mirrors how `ai_orchestrator.py` already
falls back to `HeuristicAIProvider` for guest messaging). For PDF
specifically:

- **Primary provider**: whichever model is already configured via
  `settings.openai_api_key` / `settings.openai_model` — no new provider
  wiring needed for v1.
- **Fallback on primary failure**: retry once, then mark the row
  **Needs Review** with the raw extracted text attached, rather than
  failing the whole upload. A parser exception is not a reason to lose
  the PDF's content — it's a reason to ask a human to finish the job the
  AI couldn't.
- **Cost control**: extraction happens once per PDF (or once per
  reservation for multi-reservation PDFs), and the same "zero-cost
  first" philosophy from `zero_cost_agent.py` applies conceptually —
  don't call the model for anything the digital-text-extraction step can
  answer for free (e.g., don't re-derive dates via AI if a
  straightforward text pattern already found an unambiguous ISO date).
- **Multi-provider fallback (Claude/Gemini) is explicitly out of scope
  for v1.** One well-tested provider beats three untested ones. Revisit
  if the primary provider's failure rate in production data justifies
  the added complexity — not before.

## 9. The shared Importer interface

Formalizes what CSV and manual entry already do implicitly, so PDF,
Email, and the future PMS connectors don't each reinvent it:

```python
class Importer(Protocol):
    def validate(self, raw_input) -> ValidationReport: ...
    def preview(self, raw_input) -> list[ReservationCreate]: ...
    def import_(self, raw_input, session: ImportSession) -> ImportResult: ...
    def summary(self, session: ImportSession) -> ImportSummary: ...
```

- `validate()` — CSV's version already exists (`_validate_csv_rows`).
  For PDF, this is where extraction + confidence-thresholding happens.
- `preview()` — what the Validate/Review screen renders. For CSV this is
  the raw row; for PDF this is the **Extracted Reservation** card from §7.
- `import_()` — thin wrapper around the existing `import_reservation()`
  orchestrator call. This is the one method that should barely change
  between importers, since it's already shared.
- `summary()` — already exists as `build_import_summary()`; becomes the
  default implementation every importer gets for free.

This interface is a refactor of CSV's existing functions into a named
shape, not new behavior — tracked as its own backlog item (task #32-
adjacent) so it lands as a mechanical extraction, reviewed on its own,
before PDF's `validate()`/`preview()` are written against it.

## 10. Explicitly out of scope for v1

- Multi-provider AI fallback (§8)
- OCR quality tuning beyond "does it produce usable text" (§3)
- Learning per-hotel PDF templates over time (mentioned as a future
  win in §2's "Direct booking" row, not a v1 requirement)
- Retry-failed-rows UI (tracked separately, task #28 area) — PDF rows
  that fail import for a real system reason behave like any other
  `rows_failed` case already defined by the Import Foundation

## 11. Open questions before implementation starts

1. Where does `external_id` come from for PDF-derived reservations, for
   idempotent re-upload detection (§6)? CSV generates a random UUID per
   upload; PDF needs something derived from the document's own
   confirmation number, which means the extraction schema (§5) needs a
   `confirmation_number` field even though `ReservationCreate` doesn't
   currently have anywhere to put it as a first-class field. Needs a
   decision, not an assumption.
2. PDF text extraction library choice (pdfplumber vs. pypdf vs.
   something else) — needs a quick spike against real sample PDFs from
   the five sources in §2, not a decision made in the abstract.
3. Where do uploaded PDFs live after processing — kept for audit/
   reprocessing, or discarded once extraction completes? Affects
   storage cost and whether "Download the original PDF" is possible
   from the future Import Details page.
