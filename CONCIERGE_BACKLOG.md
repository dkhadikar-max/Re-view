# AI Concierge Backlog

Status: empty by design — this file exists so Week 4 (CONCIERGE.md §12)
has somewhere to log real pilot-conversation findings from day one,
same discipline as PARSER_BACKLOG.md. Nothing goes here from internal
speculation; every line should trace back to an actual conversation
with an actual guest at an actual pilot hotel.

## P0 — Real guest-facing failures

The concierge answered wrong, should have escalated and didn't, or
crashed mid-conversation. Highest priority, same-day if needed — this
is the one tier where CONCIERGE.md §0's principle is directly at stake.

*(empty — no pilot hotels onboarded yet)*

## P1 — Escalation list gaps

A real conversation revealed a topic that should have triggered §7's
escalation gate but didn't. Per §7, this list only ever widens — a gap
found here is never "let's wait and see," it's a same-week fix.

*(empty)*

## P2 — Agent accuracy / prompt improvements

The right agent answered, correctly, but a real guest's phrasing
tripped it up, or the Router (§4) sent a message to the wrong agent.
Distinct from P0: nothing wrong was said, the experience just wasn't as
smooth as it could be.

*(empty)*

## P3 — New agent capabilities

Something a real hotel or guest asked for that none of the four agents
(§5) currently cover, and that's clearly worth a fifth capability
rather than a fix to an existing one. Only justified by observed
demand, same reasoning as PARSER_BACKLOG.md's P3 (OCR).

*(empty)*

---

**How to file something here**: hotel/guest context (anonymized if
needed), the actual message, what the concierge did, what it should
have done. Enough to turn into a fixture/regression test the way the
PDF Import review-gate fixtures worked (see PDF_IMPORT.md §12).
