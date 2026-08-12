# Guest Memory Evidence Chain — planning doc, not yet implemented

Status: **Planning only, per explicit instruction.** This answers the
five planning questions the Phase 4 (operator guest-intelligence
screen) design review asked for, grounded in the real, already-frozen
`MEMORY_MANAGER.md` contract — not a second, competing data model.
**Extends** `MEMORY_MANAGER.md`; nowhere contradicts or reopens it.
Nothing in this document is implemented. It does not authorize
resuming backend feature development on its own — `CLAUDE.md`'s
"feature development is explicitly stopped" stance stays in force
until the reader (not this document) makes that call explicitly, the
same way every other backend decision this quarter has required an
explicit "yes, implement."

---

## 0. The honest starting point

The Phase 4 v2 prototype (`revisit_phase4_v2.html`, approved as a
design direction) shows a chain: **Guest → Memory → Evidence → Hotel
intelligence → Action → Outcome.** Before planning how to build it,
it's worth being precise about which parts of that chain already exist
in the real system today, and which don't — because two of the six
nodes rest on capability that isn't built yet.

| Chain node | Real today? | Where |
|---|---|---|
| Guest (returning, stay count) | ✅ Yes | `Guest.stay_count`, already tracked |
| Memory (the current preference value) | ✅ Yes | `Guest.dietary_preferences` / `preferred_room` / `notes` |
| Evidence (the guest's literal quote) | ❌ **No** | `Message.body` stores it, but nothing links a `Guest` field's current value back to *which* message produced it (§2) |
| Hotel intelligence ("remembered") | ✅ Yes, partially | `MemoryManager`'s accept/hold/reject decision, logged to `ActionEvent` |
| Confirmed vs. inferred | ⚠️ **Confirmed-only today** | v1 has exactly one evidence source (explicit self-statement) — "inferred" (pattern across stays) is a named, deferred roadmap item, not built (§1) |
| Action (team informed / available) | ❌ No | No hotel-team notification or "available to restaurant" surface exists yet — Phase 4's own copy already says this ("available," not "informed ✓"), which turns out to be exactly right |

This isn't a reason to abandon the design — it's the actual scope of
what "implement Phase 4" means. Two real, contained gaps (§2, §3)
close most of the distance.

## 1. The guest-memory data model — mostly already frozen

`MEMORY_MANAGER.md` already is the guest-memory data model. It is not
being redefined here. As a reminder of its shape (so this document is
self-contained): three flat fields on `Guest`
(`dietary_preferences`, `preferred_room`, `notes`), each with its own
mutation policy (protected/append-only, replace-at-confidence,
append-only), written exclusively by `MemoryManager`, every decision
logged to `ActionEvent` with a `confidence` float and a
`MEMORY_PROPOSED`/`MEMORY_ACCEPTED`/`MEMORY_HELD`/`MEMORY_REJECTED`
`action_type`.

**What Phase 4 needs that isn't in that contract:** a way to answer
*"which `ActionEvent` produced the value `Guest.dietary_preferences`
currently holds, and what message triggered it?"* That's a read-path
question, not a write-policy question — `MEMORY_MANAGER.md` correctly
never had to answer it, since it only cares about writing correctly,
not about a UI displaying provenance later.

## 2. Confirmed / inferred / source / timestamp / confidence — precise semantics

- **`confidence`** — already real, already stored (`ActionEvent.confidence`, a
  `float`). No change needed. Displaying it (e.g., "92% confidence") is
  a UI decision, not a data-model one — worth deciding deliberately
  *not* to show a raw percentage to hotel staff, per the same "don't
  expose a score as if it's a fact" instinct that kept `ltv_score`
  internal elsewhere in this codebase. Confirmed/inferred as a
  **word**, not a **number**, is very likely the right call for an
  operator screen — staff don't need 0.87 vs 0.91, they need "the
  guest said this" vs "we noticed a pattern."

- **`confirmed`** — v1's only real state. Every `MEMORY_ACCEPTED` event
  today came from an explicit guest self-statement matching one of
  `GuestMemoryAgent`'s reviewed patterns. **There is no `inferred` path
  in production yet.** Building Phase 4's confirmed/inferred UI
  honestly means one of two choices, not a third option where both
  already work:
  - **(a)** Ship Phase 4 v1 showing **confirmed only** — accurate,
    smaller scope, ships sooner. The v2 prototype's own aside ("this
    one is confirmed, not inferred") already reads correctly this way
    without any code change — it's explaining a real distinction even
    though only one side of it has a live example yet.
  - **(b)** Build the deferred "order-pattern evidence track" first
    (real inference from repeated behavior, e.g. two room-change
    requests in the same direction), so `inferred` has a genuine
    example. This is real, scoped, roadmapped work — not a UI toggle.
  Recommendation: **(a)** for Phase 4's first ship. Don't build a new
  agent capability to make a design review's example richer than the
  product currently is — that's optimizing the demo over the product,
  the exact failure mode this whole review process has been guarding
  against.

- **`source`** — needs one small, real addition (§3): a link from the
  `Guest` field's current value to the `Message` that produced it.

- **`timestamp`** — already real. `ActionEvent.created_at` and
  `Message.created_at` both exist today.

## 3. The one real gap: linking a memory value back to its evidence

**Concretely:** `MemoryUpdate` (the Pydantic object `GuestMemoryAgent`
returns) carries `field`, `value`, `confidence` — no reference to the
`Message` it came from. `ActionEvent` has no `message_id` column. So
"show the guest's exact words" (the Evidence node — praised as the
single strongest part of the v2 prototype) cannot be reconstructed
from the database today, for any guest, for any preference.

**The fix is small and additive, not a redesign:**

1. Add `message_id: Optional[str]` to `MemoryUpdate` — `GuestMemoryAgent`
   already has the triggering `Message` in scope when it builds the
   update (it's reading `context.conversation_history`/the current
   turn to produce the proposal); it just isn't threading the id
   through today.
2. Thread that `message_id` into `MemoryManager.apply_or_hold`'s
   `event_metadata` — `{"field": "dietary_preferences",
   "message_id": "..."}` — which is already exactly what
   `event_metadata` is for (structured facts, never raw text,
   `MEMORY_MANAGER.md` §4). This does **not** violate the Action
   Ledger's "no raw guest text" rule — the *id* is stored, not the
   *body*; a reader joins to `Message.body` only when actually
   rendering the evidence, same indirection `input_summary` already
   uses everywhere else in this table.
3. Read path for Phase 4: given a `Guest` and a `field`, find the most
   recent `MEMORY_ACCEPTED` `ActionEvent` for that
   `(guest_id, field)` pair (already fully queryable — `event_metadata`
   is JSON, `action_type`/`guest_id` are indexed columns), pull
   `message_id` from its metadata, join to `Message.body` for the
   quote.

This is the entire schema change this plan calls for. No new table,
no new column on `Guest` or `ActionEvent` beyond the one optional
field on the in-memory `MemoryUpdate` object (which isn't even a
database row — it's the agent's return type).

## 4. Operator workflow at check-in

Not yet a real trigger anywhere in the codebase — there's no
"check-in" event today (`Reservation` has status fields, but nothing
in this repo currently fires a hook when a guest is marked
checked-in). Two honest paths:

- **(a) Pull, not push, for v1.** Front office opens a guest's profile
  (already-existing `Guest` detail view, or a new one) at or before
  check-in, manually, the way staff already look up a reservation
  today. No new trigger needed — just a screen that reads
  `Guest.dietary_preferences`/`preferred_room`/`notes` plus the
  evidence join from §3. This matches Phase 4 v2's own restraint
  around not overclaiming a live integration.
- **(b) Push, later.** A real "guest checked in" event (would need a
  `Reservation.status` transition to `checked_in`, and something
  watching for it) that surfaces preferences automatically at the
  front desk. This is meaningfully more work — a new domain event, a
  subscriber, and a decision about where it displays — and shouldn't
  be assumed as part of a "just build the screen" scope.

Recommendation: **(a)** for the first real implementation. The
cinematic story is allowed to dramatize "recognized at check-in" as an
instant, automatic moment — that's the marketing site's job. The
operator tool doesn't have to claim the same automation on day one to
be useful; a staff member opening a guest profile and seeing the
chain is already the "the guest doesn't need to repeat themselves"
outcome, even if a human chose to look.

## 5. How preferences are exposed to hotel teams

Today: **nowhere.** No notification, no PMS note, no restaurant-facing
surface exists. Phase 4's own "available for this stay" (not
"informed ✓") copy is the honest description of what a first
implementation can actually claim: **a screen a staff member can look
at**, not a push notification to another system or team. Turning
"available" into "informed" later is a distinct, larger piece of work
(§6) — a real integration with whatever system the restaurant team
actually uses, which this repo doesn't have visibility into yet.

## 6. Mapping to existing PMS/CRM architecture

`ReVisit` already syncs with Cloudbeds (PMS, priority-1 integration
per the project's own architecture notes) for reservations — but nothing
about `dietary_preferences`/`preferred_room`/`notes` flows to or from
Cloudbeds today; these are ReVisit-native `Guest` columns, not
PMS-synced fields. Two real architectural questions worth a decision,
not an assumption, before real implementation:

- Should a confirmed preference eventually **write back** to Cloudbeds
  (so it shows up in the PMS's own guest notes, visible to staff who
  never open ReVisit)? That's a real, scoped integration question —
  Cloudbeds' API surface for guest notes would need checking, and it's
  a one-way-sync-risk question (what happens if a hotel edits the note
  in Cloudbeds directly — does ReVisit's copy go stale silently?).
- Or does ReVisit stay the **single source of truth** for guest
  intelligence, with hotel teams checking a ReVisit screen instead of
  (or alongside) their PMS? This is the lower-risk default and matches
  everything built so far (ReVisit doesn't currently claim to be a
  system of record for anything PMS-owned).

Recommendation: **stay ReVisit-native** for the first implementation —
matches Phase 4's own "available for this stay," not "synced to your
PMS." A Cloudbeds write-back is real future scope, not a hidden
prerequisite.

## 7. What "implement the Phase 4 operator surface" concretely means, given all of the above

A scoped first PR, once explicitly authorized, would be:

1. `MemoryUpdate.message_id` (optional field) + threading it into
   `event_metadata` — the one real schema-adjacent change (§3).
2. A read-side query: given `(guest_id, field)`, return the current
   value, its most recent `MEMORY_ACCEPTED` event, and the linked
   `Message.body` if present (handles guests whose preference predates
   this change gracefully — evidence node simply doesn't render for
   them, chain still shows Memory/Hotel-intelligence/Action).
3. A new frontend screen (`/app/guests/:id` extension or a new route)
   rendering exactly the v2 chain — confirmed-only (§2a), "available
   for this stay" language (§5), no invented team-notification state.
4. No new agent, no new confidence model, no inferred-evidence work,
   no Cloudbeds write-back — all explicitly out of scope for this pass,
   per §2/§5/§6's recommendations above.

This document stops here. Whether to authorize step 7 is the reader's
decision, not a default this plan reaches on its own.
