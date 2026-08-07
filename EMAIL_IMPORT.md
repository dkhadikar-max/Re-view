# Email Import — Design Document

Status: Draft, not yet implemented. No code has been written against this
document, per the same discipline PDF_IMPORT.md was built under — design
first, then implementation, then a review gate before merge.

**v1 scope is deliberately narrow** (revised after co-founder review of
the first draft): PDF attachments only, reusing `PdfImporter` verbatim.
No email-body AI parsing, no HTML-inline extraction, no calendar
invites in v1 — see §10. The goal is removing PDF Import's one
remaining friction point (a hotel has to remember to leave the app,
save an attachment, come back, and upload it) with the smallest change
that reuses everything already built and reviewed.

---

## 1. Why this needs a design pass first — and why more than PDF did

PDF Import's hardest problem was AI extraction risk (the model can be
confidently wrong). Email Import's v1 scope sidesteps that entirely —
it doesn't parse anything itself, it hands a PDF attachment to the
already-reviewed `PdfImporter` (PDF_IMPORT.md). What email adds that
PDF never had is a new **trust** problem: PDF upload happens behind a
login — a manager who's already authenticated picks a file and uploads
it, so "who is allowed to create reservations for this tenant" is
already answered by the time any parsing starts. An inbound email
endpoint has no such gate by construction — it's reachable by anyone on
the internet who knows (or guesses) the address. §3 and §6 exist to
answer that, not to improve parsing (there's no new parsing here to
improve).

## 2. Transport: inbound webhook, not IMAP polling — decided

Two ways a hotel's forwarded mail could reach ReVisit:

- **Inbound webhook** (a hotel forwards to a ReVisit-owned address;
  ReVisit's email provider POSTs the message to us). ReVisit never
  holds any credential belonging to the hotel — the hotel's own mail
  provider does 100% of the work of getting mail to us, using nothing
  more than an email address, the same as forwarding to a colleague.
- **IMAP polling** (ReVisit logs into the hotel's own mailbox and pulls
  mail). This requires the hotel to hand over real mailbox credentials
  (or go through their mail provider's OAuth) — a categorically bigger
  trust ask than a forwarding address, and infrastructure ReVisit would
  have to secure and rotate credentials for, per hotel, forever.

**Decided: inbound webhook**, for v1 and probably permanently. It's
simpler to build, matches the "hotel forwards from their own inbox"
model that's already the natural workflow, and never puts ReVisit in
possession of a hotel's actual mailbox password. IMAP polling isn't
ruled out forever, but nothing in the roadmap needs it — it would only
matter for a hotel that wants zero-touch automatic forwarding via a
provider-side rule instead of a human clicking "forward" each time,
which is a real but separably-scoped improvement, not a v1 requirement.

## 3. The trust model

Every tenant gets one unique, unguessable inbound address:

```
{opaque-token}@import.revisit.ai
```

`{opaque-token}` is a random identifier (not the hotel's name or a
sequential ID) — generated once per tenant, shown once in Settings,
regenerable on demand (e.g. if a staff member who knew it leaves, or it
leaks into a mail thread forwarded somewhere it shouldn't). **The
address itself is the credential.** This system does not attempt to
verify "this really came from Booking.com" via SPF/DKIM/DMARC on the
original OTA — that verification is meaningless anyway once a human has
manually forwarded the mail (forwarding breaks the original sender's
DKIM signature by design; this is normal, expected, not a red flag).

What SPF/DKIM/DMARC results on the **inbound provider's own webhook
payload** *are* used for (most inbound-email providers surface these
per-message): a visible sanity signal on the review row, not a gate.

**Consequence of this model**: leaking the address is equivalent to
leaking an API key for "create reservations in my tenant." Settings
must treat it that way — same UI treatment as a secret/token, not a
casually-copyable "your import email" field.

## 4. Pipeline (v1)

```
Inbound email received by provider
        │
        ▼
Provider webhook → POST /webhooks/email/inbound
        │
        ▼
Resolve tenant from the opaque recipient address
(unknown/regenerated-away address → 200 OK + drop, §6)
        │
        ▼
Has a PDF attachment?
        │
   ┌────┴─────┐
   │          │
  Yes         No
   │          │
   ▼          ▼
Extract via          Needs Review, no reservation —
existing PdfImporter  "forward the original confirmation
(PDF_IMPORT.md §3)    with its PDF attached, or use
   │                  Manual Entry" (§6)
   ▼
Same Validator → Review → Import Orchestrator path
PDF_IMPORT.md already goes through — verbatim, not
reimplemented. ImportSession.source = "email" (not "pdf")
so Import History still shows accurately where each
reservation actually arrived from, even though extraction
code is shared with PDF.

   (Future, not v1 — see §10)
   ┌──────────────────────┐
   │ ICS / calendar invite │
   │ Inline body-text AI   │
   │ parsing (no PDF)      │
   └──────────────────────┘
```

This is the co-founder's own diagram for the milestone, and it's the
right one: `Importer` and Import Orchestrator are reused exactly as
PDF_IMPORT.md §9 already established — Email is another ingestion
source into the same pipeline, not a parallel one.

## 5. Extraction schema

Unchanged — whatever `PdfImporter` already produces (PDF_IMPORT.md §5).
Nothing new to define; v1 email import contributes no schema of its
own.

## 6. Error cases

| Case | Handling |
|---|---|
| Unknown/regenerated-away recipient address | `200 OK`, drop silently — never a distinguishable error code, so the address space can't be probed by watching for a different response |
| No PDF attachment on the email | **Needs Review**, no reservation extracted — message points at Manual Entry or "forward again with the confirmation PDF attached" rather than silently discarding the email |
| PDF attachment is password-protected/corrupt/oversized/too-many-pages | Same specific errors `PdfImporter` already raises (PDF_IMPORT.md §6), surfaced on the inbox row |
| Multiple attachments, more than one is a PDF | v1: process the first valid PDF only, flag the row so a human notices there were others — not a silent "pick one" |
| Duplicate (same confirmation forwarded twice, or already imported via CSV/PDF/manual) | Same `external_id` fallback hierarchy as PDF_IMPORT.md §11.1 — a confirmation number extracted from an emailed PDF collapses to the same `external_id` as the same PDF uploaded directly, on purpose |
| Non-PDF attachment (zip, exe, docx, image) | Ignored for extraction, never executed or served back |
| Mailbomb/spam flood to one tenant's address | Rate-limited per tenant (needs a real number — §11); beyond it, accept-and-drop, same non-probeable-response principle |

## 7. Review UI

An **Email Import inbox** — not a step in the existing `/import`
wizard, because nobody is present synchronously when the email arrives.
List of received messages: sender, subject, received time, Ready to
Import / Needs Review. Since v1 only ever extracts via `PdfImporter`,
each row's Extracted Reservation card is *identical* to PDF's review
card (PDF_IMPORT.md §7) — Approve / Edit-then-Approve, never
auto-import. `/import/history` remains the cross-source audit trail;
this inbox is the per-message queue feeding it.

## 8. AI provider, cost, and fallback

N/A for v1 — there is no new AI call. `PdfImporter`'s existing AI
Parser (PDF_IMPORT.md §8) runs unmodified on the attachment.

## 9. The shared Importer interface

`EmailImporter` becomes the second implementation of the Protocol
defined in `app/services/importer.py`, after `PdfImporter` — and for
v1, a genuinely thin one: `validate()`/`preview()` unwrap the webhook
payload to find a PDF attachment and delegate straight to
`PdfImporter.validate()`; `import_()` creates an `ImportSession` with
`source="email"` and otherwise calls the same `import_reservation()`
call PDF's `import_()` does. There is no new extraction logic to write
in v1 — only routing and the trust boundary (§3).

## 10. Explicitly out of scope for v1

- **Email-body AI parsing** (no attachment, reservation details only in
  the message text). This was the bulk of the original draft's scope
  and is deliberately cut — it's the one part of Email Import that
  would have needed new extraction logic and new review-UI surface
  beyond what PDF already built. Revisit once PDF-attachment-only
  volume from real hotels shows body-only forwards are common enough to
  justify it.
- **ICS/calendar invites** — a real future ingestion source (per the
  milestone diagram) but a different attachment type with its own
  schema (iCalendar, not free text), not built now.
- **IMAP polling** — see §2; not ruled out forever, no current need.
- **HTML-inline extraction, multiple-attachment-type handling beyond
  "first PDF wins," custom per-hotel forwarding rules** — same
  reasoning as the original draft's out-of-scope list.
- **Two-way email** (replying to a hotel, emailing guests) — inbound
  ingestion only; outbound stays exactly as `email_providers.py`
  already handles it.

## 11. Open questions before implementation starts

1. **Inbound email provider.** Needs an actual inbound-receiving
   service — outbound (`resend`/`postmark` in `config.py`) is a
   different capability. Postmark has Inbound Processing and the app
   already has a Postmark outbound path (one vendor relationship
   instead of two); Mailgun Routes and SendGrid Inbound Parse are the
   other common choices. Needs a decision plus DNS access on whatever
   domain receives the mail (`argusai.online` or a subdomain) —
   infrastructure this assistant can design around but can't provision.
2. **Per-tenant rate limit** for §6's mailbomb case — a real number,
   not a guess, ideally informed by what legitimate pilot-hotel
   forwarding volume actually looks like.
3. **Where the opaque per-tenant address lives in Settings**, and what
   "regenerate" invalidates immediately vs. with a grace period.
