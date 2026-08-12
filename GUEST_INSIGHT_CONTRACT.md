# Guest Insight Contract — §1, FROZEN

Status: **Frozen v1 contract**, converged over two rounds with a
full markup. Same discipline as `GUEST_MEMORY_EVIDENCE_CHAIN.md` and
`PHASE4_PRODUCT_REVIEW.md`: grounded in the real, already-frozen
contracts this extends, never contradicts. Authorizes exactly the
implementation scope in §Freeze below — nothing broader.

---

## Decision 1 — Dietary conflicts: surface tension, never silently supersede

`MemoryManager._apply_dietary` is unchanged and stays authoritative:
"protected... never silently replaces an existing value at any
confidence; only ever appends... leaves normalization to staff."
Guest Insight is a **read-side layer over that unchanged behavior**,
never a second write path.

- **Memory layer** — unchanged. `Guest.dietary_preferences` keeps
  appending, exactly as `MEMORY_MANAGER.md` already specifies.
- **Evidence layer** — unchanged. Both accepted statements remain in
  the ledger, exactly as Phase 4A already stores them.
- **Insight layer** — detects an explicit, narrow conflict and
  surfaces it as **Needs review**. Never claims to know which
  statement is the guest's current truth.
- **Operator action** — staff resolves it with the guest directly.
  No automatic mutation, ever.

Wording, exact: never say a statement is "wrong." Say **conflicting
evidence**:

> **Dietary preference — Needs review**
> Guest previously stated "vegetarian" (14 Jun). Guest more recently
> stated "eating meat again" (12 Aug).
> **Conflicting guest statements — review with guest before relying
> on this preference.**

Conflict detection is deliberately narrow — **explicitly incompatible
accepted dietary evidence**, never "two different dietary
observations" (that would turn ordinary cumulative preferences, e.g.
"vegetarian" + "allergic to peanuts", into false conflicts).

**Grounding check that changes the freeze, below:** given that
narrow definition, there is currently no real, deterministic trigger
for it. See §Open finding.

## Decision 2 — Persistence/expiry: deferred to v2

Frozen: **v1 persistence model is exactly Phase 4A's existing
behavior — everything accepted stays persistent. No `expires_at`,
`review_at`, Stay-specific, Event-specific, or automated freshness
lifecycle in this PR.** No placeholder fields added "for future use"
— an unused column implies a capability that doesn't exist. Step 6's
lifecycle categories are documented here as **future-state concepts**,
not v1 capabilities.

## Clarification A — Evidence → Insight → Recommended action, not rewritten evidence

Frozen hierarchy:

**Evidence → Insight → Recommended action**

Never **Evidence → rewritten/normalized evidence → Insight**. Guest
Insight is a summary layer *above* the existing, unchanged,
collapsible Evidence Chain cards (Phase 4A) — reusing them verbatim,
not replacing or renormalizing them. An operator clicking through must
see exactly the evidence that produced the insight, preserving Phase
4A's evidence-chain principle unchanged.

## Clarification B — `category` backfill: deterministic from source field only

`MemoryEvidence.category` is set only where the source field already
establishes one:

- `dietary_preferences` → `Dining`
- `preferred_room` → `Room`
- everything else → `null` / uncategorized

**No backfill from free-form interpretation of `notes`.** `notes`
stays excluded from the Evidence Chain, exactly as Phase 4A already
decided (append-only free text, no single current value) — this PR
does not sneak that inference back in through category assignment.

## Clarification C — the four-state taxonomy, precise meanings

| State | Meaning |
|---|---|
| **Confirmed** | Evidence supports the displayed insight, no detected protected-field conflict. |
| **Needs review** | Evidence contains an explicit, narrow, unresolved conflict relevant to the insight. *(See Open finding — currently a defined, dormant state; no real trigger exists yet.)* |
| **Empty** | No qualifying evidence exists. Must never be read as "no preference" — it means "nothing stated," not "guest has none." |
| **Not tracked** | The system does not currently have the evidence needed to make the claim (mirrors the Evidence Chain's existing "no linked message on record" and Outcome's "not tracked yet" language). Must never be read as "nothing happened." |

---

## Open finding — "Needs review" has no real trigger under "no new memory semantics"

`GuestMemoryAgent`'s dietary patterns are a fixed, closed vocabulary —
Vegetarian, Vegan, Gluten-free, Lactose-intolerant, Pescatarian,
Halal, Kosher, plus free-text "Allergic to X" — and **none of these
are opposites of one another**. A guest can genuinely hold several at
once. There is no "no longer vegetarian" / "eating meat now" pattern
in the agent today, so the conflict example in Decision 1 isn't
something the real system can currently produce.

Two honest paths, genuinely in tension with each other:

- Give "Needs review" a real trigger → requires adding a new
  recognized pattern to `GuestMemoryAgent` (a memory-layer change).
- Keep "no new memory semantics" → "Needs review" ships as a named,
  defined, currently-dormant state — same shape as an unused
  epistemic tier in `PHASE4_PRODUCT_REVIEW.md`'s taxonomy.

**Frozen resolution: the second.** "Needs review" is part of the v1
taxonomy (Clarification C) with exact wording (Decision 1), but ships
with **no working trigger** in this PR. Real dietary-conflict
detection is named here as explicitly future, scoped work — a
deliberate `GuestMemoryAgent` pattern addition, decided and reviewed
on its own, not a side effect of this PR.

---

## Freeze — the first implementation PR, exactly this and nothing else

**Backend**
- `category: Optional[str]` added to `MemoryEvidence`
  (`guest_memory_evidence.py`) — deterministic mapping per
  Clarification B, no new table.
- No changes to `MemoryManager`, `GuestMemoryAgent`, or any write
  path.
- No conflict-detection logic (Open finding) — `needs_review` is not
  a value any code path produces in this PR.

**Frontend**
- A Guest Insight summary line above the existing (unchanged)
  Evidence Chain, built from the same `category` + existing fields.
- No new "Needs review" UI state rendered yet, since nothing produces
  it — the four-state taxonomy is documented (Clarification C) for
  the next PR that adds a real trigger, not built speculatively now.

**Tests**
- `category` assignment: dietary → Dining, room → Room, mirrors
  existing Phase 4A test conventions.
- Tenant isolation (existing pattern, every test file this session).
- Empty-state guest still renders correctly with the new field absent.

**Not in this PR:** `MemoryManager` write-path changes, expiry
machinery, new memory semantics (including any new `GuestMemoryAgent`
pattern), reinterpretation of `notes`, outcome tracking, "AI"
terminology, predictive scoring, cross-hotel memory, sentiment
profiling, autonomous offers, automated marketing, a new agent, a
recommendation engine.

This extends Phase 4A without reopening any of its safety decisions,
and ships only what the system can currently do honestly.
