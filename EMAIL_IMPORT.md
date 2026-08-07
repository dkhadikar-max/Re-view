# Email Import — Design Document

Status: Draft, not yet implemented. No code has been written against this
document, per the same discipline PDF_IMPORT.md was built under — design
first, then implementation, then a review gate before merge.

---

## 1. Why this needs a design pass first — and why more than PDF did

PDF Import's hardest problem was AI extraction risk (the model can be
confidently wrong). Email Import inherits that exact same problem
(reuses the same AI Parser, §8) **plus** a new one PDF never had: PDF
upload happens behind a login — a manager who's already authenticated
picks a file and uploads it, so "who is allowed to create reservations
for this tenant" is already answered by the time any parsing starts.
Email has no such gate. A `POST /webhooks/email/inbound` endpoint is,
by definition, reachable by anyone on the internet who knows (or
guesses) the address. Before any extraction-quality question, this
needs a real answer: **what stops a stranger from emailing a fake
reservation into a hotel's guest list?** §3 and §6 exist mainly to
answer that, not to improve parsing.

## 2. Supported sources (v1)

| Source | How it arrives | Notes |
|---|---|---|
| Booking.com confirmation, forwarded | Hotel forwards from their own inbox | Body text usually has the full confirmation inline |
| Airbnb confirmation, forwarded | Hotel forwards from their own inbox | Same |
| Expedia confirmation, forwarded | Hotel forwards from their own inbox | Same |
| Any confirmation with a PDF attached | Forwarded email whose body is just a wrapper, real content is an attached PDF | Common — OTAs frequently attach the actual confirmation rather than inlining it |
| Hotel's own reservation system, forwarded | Hotel forwards from their own PMS/booking widget's notification email | Format varies per hotel, same caveat as PDF §2's "Direct booking" row |

A hotel **forwards** mail to their own unique ReVisit address — this
system never receives mail directly from Booking.com/Airbnb/Expedia's
servers, and never claims to. That distinction matters for §3.

Anything that isn't a booking confirmation (a newsletter, a spam email
accidentally forwarded) is an **error case** (§6), not a sixth format.

## 3. The trust model — this is the actual design problem

Every tenant gets one unique, unguessable inbound address:

```
{opaque-token}@import.revisit.ai
```

`{opaque-token}` is a random identifier (not the hotel's name or a
sequential ID) — generated once per tenant, shown once in Settings,
regenerable on demand (e.g. if a staff member who knew it leaves, or it
leaks into a mail thread that gets forwarded somewhere it shouldn't).
**The address itself is the credential.** This system does not attempt
to verify "this really came from Booking.com" via SPF/DKIM/DMARC on the
original OTA — that verification is meaningless anyway once a human has
manually forwarded the mail (forwarding breaks the original sender's
DKIM signature by design; this is normal, expected, and not a red flag).

What SPF/DKIM/DMARC results on the **inbound provider's own webhook
payload** *are* used for (most inbound-email providers surface these
per-message): a sanity signal for the review screen, not a gate.
"Sender authentication: failed" next to a Needs Review row is useful
context for a human; it is not, by itself, a reason to silently drop or
silently accept a message. The address being correct is the real gate;
everything after that is the same Ready/Needs Review pipeline PDF
already has.

**Consequence of this model**: leaking the address is equivalent to
leaking an API key for "create reservations in my tenant." Settings
must treat it that way — same UI treatment as a secret/token, not a
casually-copyable "your import email" field.

## 4. Pipeline

Reuses the Import Foundation and the PDF Import work exactly — Email is
a new *Importer*, not a new destination, and where the source data is a
PDF attachment, it's literally the same `PdfImporter` extraction path.

```
Inbound email received by provider (e.g. Postmark Inbound)
    │
    ▼
Provider webhook → POST /webhooks/email/inbound
    │
    ▼
Resolve tenant from the opaque recipient address
(unknown/regenerated-away address → 200 OK + drop, not an error the
 sender should be able to probe for — see §6)
    │
    ▼
Has a PDF attachment?
    │
    ├── Yes ──→ Extract via the existing PdfImporter pipeline
    │           (PDF_IMPORT.md §3) — literally the same code path
    │
    └── No ───→ Extract plain text from the email body
                          │
                          ▼
                   AI Parser (same as PDF_IMPORT.md §8 —
                   identical prompt/schema/fallback contract,
                   reused, not reimplemented)
                          │
                          ▼
              Normalized ReservationCreate
             (same schema every importer produces)
                          │
                          ▼
                     Validator
             (shared logic — see PDF_IMPORT.md §9's
              Importer Protocol; EmailImporter implements it)
                          │
                          ▼
             Needs Review inbox (§7 — NOT immediate,
             see below for why this differs from "review before
             import" as a live UI flow)
                          │
                          ▼
       Import Orchestrator → Guest Service → Reservation Service
       → Automation Engine (100% unchanged, same as every source)
```

**Important difference from PDF's review flow**: PDF's reviewer is the
same person who just uploaded the file, sitting at the Review screen
that instant. Email's "reviewer" isn't present when the email arrives —
it's async. So "mandatory review before import" here means: every
extracted email lands in an **Email Import inbox** (a new list view,
same shape as Import History) showing Ready to Import / Needs Review
per message, and a hotel manager reviews/approves in their own time —
not that the webhook blocks waiting for a human. This is a real
difference from PDF_IMPORT.md §7's synchronous flow and needs to be
sized as its own UI surface, not squeezed into the existing `/import`
step machine.

## 5. Extraction schema

Unchanged from PDF_IMPORT.md §5 — the AI Parser's job is still just
mapping free text onto `ReservationCreate`. No new fields. If the email
has a PDF attachment, extraction *is* PDF_IMPORT.md §5 verbatim.

## 6. Error cases (must be handled explicitly, not silently swallowed)

| Case | Handling |
|---|---|
| Unknown/regenerated-away recipient address | Return `200 OK` and drop silently — **do not** return 404/422, which would let someone brute-force-probe for valid tenant addresses by watching for a different response code |
| Email has no discernible reservation content | **Needs Review**, same as PDF's "could not identify a reservation" case, with the raw body shown |
| Sender authentication (SPF/DKIM/DMARC) failed per the inbound provider | Surfaced as a visible flag on the Needs Review row — not auto-rejected (forwarding legitimately breaks original DKIM, see §3), not auto-trusted either |
| PDF attachment present but password-protected/corrupt/oversized | Same specific errors as PDF_IMPORT.md §6, surfaced on the inbox row rather than upload-time (nobody's waiting synchronously) |
| Duplicate (same confirmation forwarded twice, or already imported via CSV/PDF/manual) | Same `external_id` fallback hierarchy as PDF_IMPORT.md §11.1 — confirmation number hash first, content hash fallback. This is genuinely valuable here: a hotel might paste the same PDF into both the PDF upload flow *and* forward the confirmation email — the identical `confirmation_number` collapses both into one reservation, not two |
| Attachment is a large/unexpected file type (zip, exe, etc.) | Ignored for extraction purposes, never executed or served back; only PDF/plain-text attachments are inspected at all |
| Mailbomb / spam flood to one tenant's address | Rate-limit per tenant address (needs a number — §11 open question); beyond it, accept-and-drop rather than erroring, same non-probeable-response principle as the unknown-address case |

None of these should ever result in a row being imported unreviewed —
same hard rule as PDF (§7), enforced via the inbox model in §4.

## 7. Review UI

An **Email Import inbox**, not a step in the existing `/import` wizard:
list of received messages, each showing sender, subject, received time,
Ready to Import / Needs Review, and (if extracted) an Extracted
Reservation card identical in shape to PDF's (PDF_IMPORT.md §7) —
Approve / Edit-then-Approve, never auto-import. `/import/history`
already exists as the cross-source audit trail; this inbox is the
per-message queue that feeds it, analogous to how `/connectors/import-
pdf/extract` feeds a review screen before anything reaches Import
History.

## 8. AI provider, cost, and fallback

Identical to PDF_IMPORT.md §8 — same `AIGateway` contract, same
heuristic fallback, same "don't call the model for what regex can
answer for free" philosophy. No new provider wiring.

## 9. The shared Importer interface

`EmailImporter` becomes the second real implementation of the Protocol
defined in `app/services/importer.py` (PDF_IMPORT.md §9), after
`PdfImporter`. Its `import_()` reuses `import_reservation()` exactly
like PDF's does; its `validate()`/`preview()` differ from PDF's only in
where the raw bytes come from (a webhook payload vs. an upload) and in
being async/queued rather than synchronous (§4, §7).

## 10. Explicitly out of scope for v1

- **Two-way email** (replying to a hotel's forwarded email, or emailing
  a guest confirmation back) — this is *inbound only*, ingestion, not a
  new outbound channel. Outbound stays exactly as `email_providers.py`
  already handles it today.
- **Verifying the original OTA's authenticity end-to-end** (see §3) —
  the address is the trust boundary, not sender verification.
- **Parsing arbitrary forwarded-thread noise** (quoted reply chains, a
  hotel's own "FYI, see below" preamble) beyond what the AI Parser
  already tolerates in free text. If accuracy on real forwarded threads
  turns out to need thread-stripping preprocessing, that's a fast-follow
  once real pilot mail is seen — not designed blind here.
- **Non-PDF attachment types** (a .docx confirmation, a screenshot
  image) — only PDF attachments get the PdfImporter handoff in v1;
  anything else is ignored for extraction (§6).
- **Custom per-hotel forwarding rules or filters** — v1 is "forward
  everything you want imported to this one address," not a rules
  engine deciding what to forward.

## 11. Open questions before implementation starts

1. **Inbound email provider.** This needs an actual inbound-receiving
   service — outbound (`resend`/`postmark` in `config.py`) is a
   different capability. Postmark has Inbound Processing and the app
   already has a Postmark outbound integration path, which would mean
   one vendor relationship instead of two; Mailgun Routes and SendGrid
   Inbound Parse are the other common choices. Needs a decision plus
   whoever owns `argusai.online`'s DNS to add the receiving MX records —
   infrastructure this assistant can design around but can't provision.
2. **Per-tenant rate limit.** §6's mailbomb case needs a real number
   (e.g. 50 messages/hour/tenant?) — a guess isn't a substitute for
   knowing what a legitimate hotel's forwarding volume looks like, which
   nobody knows yet without pilot data.
3. **Where does the opaque per-tenant address live in Settings**, and
   what does "regenerate" actually invalidate — does the old address
   bounce immediately, or grace-period first? Affects how big a deal a
   leaked address actually is in practice.
