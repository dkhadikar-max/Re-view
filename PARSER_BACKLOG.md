# PDF/Import Parser Backlog

Status: the import pipeline (PDF_IMPORT.md) is **frozen** as of v1.2-beta.
No parser tweaks land here unless one of the tiers below justifies it —
specifically, no more hypothetical-format or hypothetical-accuracy work.
The five synthetic fixtures used during the PR #9 review gate proved the
pipeline works; only real hotel documents get to change it from here.

Priority order when something *does* come up:

## P0 — Real customer parsing failures

A pilot hotel uploaded a real document and it extracted wrong, extracted
nothing, or crashed. Always highest priority — this is the only tier
that gets worked on reactively, same day if needed.

*(empty — no pilot hotels onboarded yet)*

## P1 — Additional OTA formats

A real hotel showed us a booking-confirmation shape from a source
PDF_IMPORT.md §2 doesn't cover yet (Agoda, Hotels.com, a regional OTA,
etc.). Not urgent until it's blocking an actual hotel's actual import —
tracked here so it doesn't get built speculatively first.

*(empty)*

## P2 — Parser accuracy improvements

The heuristic (no-API-key) or AI-Parser extraction runs but gets a
field wrong or low-confidence on a real document that a human reviewer
had to correct. Distinct from P0: the pipeline didn't fail, it just
wasn't as accurate as it could be. Worth fixing once there's a pattern
across multiple real documents, not after one.

*(empty)*

## P3 — OCR support

PDF_IMPORT.md §10 already explicitly deferred this — v1 routes
no-text-layer PDFs to Needs Review pointing at Manual Entry instead of
faking OCR. Only build this if real pilot volume shows scanned/
image-only PDFs are common enough to justify it (a Tesseract dependency
or a paid OCR API is real infrastructure and real cost — see
PDF_IMPORT.md §3's "digital-first, OCR-only-when-needed" reasoning,
which still holds).

*(empty — no scanned-PDF volume data yet)*

---

**How to file something here**: when a real hotel's document exposes an
issue, add one line under the right tier with the hotel (or a
description if anonymized), the document type, and what went wrong —
enough for whoever picks it up to reproduce it as a fixture, the same
way the PR #9 review-gate fixtures were built. Move it to "done" (or
just delete the line) once fixed and re-verified against that fixture.
