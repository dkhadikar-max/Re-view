# Memory Manager — frozen v1 contract

Status: **Frozen spec, ready for implementation.** Every decision below
was reviewed and locked before writing code, same discipline
`CONCIERGE.md` §15/§16 (Action Ledger, Conversation Manager) were
built under. Implementation should not deviate from this document
without a review round the same way `action_type`/`actor` required one
(CONCIERGE.md §15's own framing: "changing these later should require
a design review, not just a code change").

**Supersedes CONCIERGE.md §5.2's "every write needs manager approval"
framing.** That was written before the Action Ledger's confidence-band
policy existed. v1 auto-applies high-confidence proposals directly
(§2 below) — the safety net is the field-specific mutation rules (§3)
and the immutable ledger record (§5), not a blanket human-in-the-loop
requirement for every note. §5.2 will be updated to point here once
this ships.

## 0. The write boundary

**`GuestMemoryAgent` proposes. `MemoryManager` is the only component
that ever calls `db.add`/`setattr` on a `Guest` row for a memory
update.** The agent's `answer()` already only returns
`AgentResponse.metadata["memory_updates"]` — a list of `{field, value,
confidence}` dicts (`guest_memory_agent.py`'s `MemoryUpdate`) — and
never touches the database. Nothing about that changes; Memory Manager
is the missing other half CONCIERGE.md's own diagram has left as "not
yet built" since the agent shipped.

## 1. Evidence sources — v1 handles exactly one

Only `GuestMemoryAgent.memory_updates` — an explicit, literal
self-statement matching one of the agent's own reviewed patterns
(`_DIETARY_PATTERNS`, `_ALLERGY_PATTERN`, `_ROOM_PREFERENCE_PATTERNS`,
`_NOTE_WORTHY_PATTERNS`). "I'm vegetarian" is evidence; a guest's
repeated room-service orders implying a dietary pattern is not — that
evidence source (roadmap task "Guest Memory: order-pattern evidence
track") stays unbuilt and out of scope. Memory Manager's own interface
should not assume it's the only future producer, but v1 has exactly
one caller and is not designed around a second one that doesn't exist
yet.

## 2. Confidence policy

Fixed bands, not a computed score — matching every other deterministic
component in this codebase (Escalation Filter, FAQ Agent, the agent's
own fixed per-pattern confidences):

| Confidence | v1 behavior |
|---|---|
| ≥ 0.85 | Auto-apply, subject to the field-specific rules in §3 |
| 0.70 – 0.84 | Hold for staff review — create a `Task`, do not mutate `Guest` |
| < 0.70 | Do not apply, do not hold (unreachable today — the agent's lowest pattern confidence is 0.75; documented for completeness, not engineered around) |

**Confidence never overrides a field's own safety rule.** A 0.95
dietary proposal still cannot silently replace an existing dietary
value — §3's field rules are a second, independent gate, not something
a high enough confidence can bypass.

**Implementation note (discovered writing the test suite, not a change
to the policy above): `preferred_room` and `notes` never reach
auto-apply today.** `GuestMemoryAgent`'s own pattern confidences for
those two fields (`_ROOM_PREFERENCE_PATTERNS`: 0.75–0.8;
`_NOTE_WORTHY_PATTERNS`: 0.75) are all below the 0.85 threshold — every
real room-preference or note-worthy statement lands in the hold band,
never auto-applies, until the agent's own patterns are recalibrated
(a `guest_memory_agent.py` change, out of scope here). Only
`dietary_preferences` (0.85–0.9 across every pattern) reaches
auto-apply in practice. Memory Manager's own logic is unchanged by
this — the confidence bands in the table above are correct and
field-agnostic by design — this is a fact about the *agent's* current
calibration, not a gap in this contract.

## 3. Field-specific mutation rules

Every field `GuestMemoryAgent` can propose today is a flat, single-value
column (`Guest.dietary_preferences: String(255)`,
`Guest.preferred_room: String(128)`, `Guest.notes: Text`) — there is no
structured list to merge into, so each field gets its own explicit
policy rather than one generic "overwrite if confident enough" rule.

### `dietary_preferences` — protected

- Empty → set to the proposed value.
- Existing value present → **append** the new fact
  (`"Vegetarian; Allergic to peanuts"`), never replace.
- Case-insensitive substring of the new value already present in the
  existing value → **ignore** (idempotent — see §6).
- **Never automatically replaces an existing value, at any
  confidence.** Losing "allergic to peanuts" because a later message
  said "I'm vegetarian" is a safety failure, not a UX inconvenience —
  this is the one field where silence (ignoring a redundant or
  lower-value proposal) is always safer than a guess.
- **No semantic relationship is inferred between values.** "Vegan"
  proposed after an existing "Vegetarian" value does **not** collapse
  or replace — it appends as a second clause, exactly like any other
  pair of facts. Recognizing that vegan implies vegetarian is exactly
  the kind of interpretation this system has deliberately avoided
  everywhere else (FAQ Agent templates a stored fact instead of
  phrasing it; Revenue Agent selects from a catalog instead of
  inventing a price) — v1 stores the guest's own words and leaves
  normalization to staff.

### `preferred_room` — not protected

- Empty → set to the proposed value.
- Existing value present → **replace** with the new value, but only at
  ≥ 0.85 confidence (the 0.70–0.84 band still goes to staff review per
  §2, same as any other field — a "held" proposal is never applied
  early just because this field is lower-stakes). The guest's most
  recently and explicitly stated preference is the one to honor; a
  wrong room preference costs nothing like a wrong dietary fact does.

### `notes` — not protected, append-only

- **Always append**, never overwrite, regardless of whether a value is
  already present.
- Each appended entry is timestamped, so provenance is legible later
  (`"[2026-08-08] Guest mentioned wanting a late checkout"`), matching
  how `messaging.py`'s inbound-WhatsApp handler already appends to this
  same field.

## 4. Action Ledger integration

Extends CONCIERGE.md §15's frozen `action_type` table with one new
value — a deliberate, documented addition per that section's own rule,
not an ad-hoc string:

| `action_type` | `actor` | Meaning |
|---|---|---|
| `MEMORY_PROPOSED` | `AI` | Already live — `GuestMemoryAgent` proposed an update (Router-logged, unchanged) |
| `MEMORY_ACCEPTED` | `SYSTEM` | Memory Manager applied the update to `Guest` |
| `MEMORY_REJECTED` | `SYSTEM` | Memory Manager decided **not** to accept the proposal (confidence < 0.70, or a `dietary_preferences` duplicate ignored per §3) |
| **`MEMORY_HELD`** (new) | `SYSTEM` | Memory Manager accepted the proposal as plausibly useful but requires a human to apply it — a staff `Task` is created, `Guest` is **not** mutated |

`REJECTED` and `HELD` are kept semantically distinct on purpose: one
means "policy decided this isn't worth keeping," the other means
"policy thinks this might matter but a human has to decide." Collapsing
them into one value would blur exactly the signal Argus's training
data needs — "what did the AI propose, what did policy do with it, and
when did policy defer to a human" are three different facts, not two.

`actor=SYSTEM` for every Memory Manager decision (`ACCEPTED`/
`REJECTED`/`HELD`) — none of these involve a guest confirming anything
(unlike Conversation Manager's `OFFER_ACCEPTED`, which is `actor=GUEST`
because a guest actually replied) or a staff member acting yet (that
would be logged separately, once a staff-completion flow exists, same
gap Conversation Manager's `TASK_COMPLETED` already has).

`event_metadata` carries the **reason/category**, never raw guest text:
`{"field": "dietary_preferences", "reason": "duplicate_ignored"}` or
`{"field": "preferred_room", "reason": "confidence_below_threshold",
"confidence": 0.78}` — structured enough for Argus to learn from,
never a copy of what the guest actually said (the Action Ledger's own
"no raw prompts" rule, CONCIERGE.md §15).

## 5. Transactional guarantee

The `Guest` mutation (when accepted) and its `MEMORY_ACCEPTED` event
are written in the **same database transaction** — one succeeds only if
the other does. A `Guest` update that silently isn't reflected in the
ledger (or a ledger event with no corresponding mutation) is a
correctness bug, not an acceptable edge case, given the ledger is
meant to be a complete, trustworthy record of what actually happened.
`HELD`/`REJECTED` paths don't mutate `Guest` at all, so this guarantee
only has teeth on the `ACCEPTED` path — but that's exactly the path
where a mismatch would be most misleading.

## 6. Idempotency

Re-proposing the same fact (a guest repeats themselves, or the same
message gets processed twice) must not create a duplicate. v1 uses a
case-insensitive substring check against the field's current stored
value — sufficient given these are short guest-facing text fields, not
a structured list, and deliberately not smarter than that: normalizing
beyond case (e.g. stemming, synonym matching) would be interpreting the
guest's words, the same over-reach §3 already rules out for dietary
values.

## 7. Tenant / guest isolation

Memory Manager never runs its own guest lookup. It receives the
already-scoped `tenant_id`/`guest_id` from the `ActionEvent` the Router
just logged (same pattern `ConversationManager.register_proposal`
already uses) and verifies the `Guest` row it loads belongs to that
`tenant_id` before any mutation — no generic cross-tenant query surface
exists at any point.

## 8. Router integration

```
Guest message
        ↓
Intent Classifier → MEMORY
        ↓
Guest Memory Agent  (proposes memory_updates, writes nothing)
        ↓
Router logs MEMORY_PROPOSED (actor=AI, unchanged from today)
        ↓
Memory Manager.apply_or_hold(db, event, memory_updates)
        │
        ├── ACCEPT → mutate Guest → log MEMORY_ACCEPTED   (same transaction)
        ├── HOLD   → create staff Task → log MEMORY_HELD
        └── REJECT → no mutation → log MEMORY_REJECTED
```

Synchronous, same turn — unlike Conversation Manager's offers, a memory
proposal never waits on a guest's reply, so no `PendingAction` is
involved here. `GuestMemoryAgent` remains structurally incapable of
writing `Guest` itself; only `MemoryManager` does.

## 9. Explicit non-goals for v1

- No order-pattern evidence (§1).
- No LLM call anywhere inside Memory Manager.
- No semantic dietary reasoning (vegan/vegetarian or any other
  relationship) — store the guest's own words verbatim (§3).
- No direct `Guest` writes from any agent.
- No blurred Action Ledger semantics — `REJECTED` and `HELD` stay
  distinct (§4).

## 10. Tests required before merge

- Confidence-band routing: ≥0.85 auto-applies, 0.70–0.84 holds, <0.70
  rejects (synthetic case, since the agent can't currently emit one).
- Dietary safety: an existing `dietary_preferences` value is never
  overwritten, including by a ≥0.85 proposal — only ever appended or
  left alone.
- Dietary append: empty → set; existing → append; case-insensitive
  duplicate → ignored, `MEMORY_REJECTED` logged.
- Preferred room replace: existing value replaced only at ≥0.85;
  0.70–0.84 holds instead of replacing early.
- Notes: always appended, timestamped, prior entries never lost.
- Idempotency: identical proposal submitted twice never double-applies.
- Tenant isolation: a `Guest` in another tenant is never reachable or
  mutated.
- **Transaction consistency**: a forced failure writing the
  `ActionEvent` rolls back the `Guest` mutation (and vice versa) — the
  two never diverge.
- Action Ledger shape: `MEMORY_PROPOSED`/`ACCEPTED`/`REJECTED`/`HELD`
  all carry `actor` correctly, and `event_metadata` never contains raw
  guest text.
- Router integration: the full `GuestMemoryAgent → MemoryManager` path
  produces the right ledger sequence for an accept, a hold, and a
  reject, end to end.
