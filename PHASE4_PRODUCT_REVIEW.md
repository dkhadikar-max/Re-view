# Phase 4 Product Review — converged draft, still not implemented

Status: **Draft, round 2 — incorporates a full section-by-section
markup. Still not frozen, still does not authorize any
implementation, still not committed to git.** Same discipline as
`GUEST_MEMORY_EVIDENCE_CHAIN.md`: grounded in what the real, current
codebase does, not in what the UI implies.

---

## Product Truth Principle — governing rule, not a footnote

> **ReVisit must never communicate more certainty, evidence,
> capability, or predictive validity than the underlying system
> actually possesses.**

This sits above every section below, not folded into the closing
notes. It covers three separate failure modes this review found, not
one:

- **Evidence** — "the guest said this" must never look the same as
  "we inferred this" (§1, §2).
- **Prediction** — a `69%` on screen must never look the same whether
  it's a calibrated probability or a hand-tuned heuristic (§4).
- **Action** — "Draft upsell →" must never look clickable unless
  clicking it actually does something (§3).

A single standard, applied three ways. Every section below is really
just this principle applied to one surface of the app.

## 0. The transition this review is about

Phase 4A (merged, `main @ a0fc10f`) answered "can ReVisit remember?"
for exactly two fields (`dietary_preferences`, `preferred_room`),
confirmed-only, with real evidence. That question is closed for that
scope. This review is the next one — and reading the rest of the app
against the same standard surfaced two concrete, current defects, not
future risks: the dead Next Best Action links (§3) and the unlabeled
heuristic numbers (§4).

## 1. Guest Insight — the epistemic model, not just a name

**Kept from round 1:** the core split between evidence-grounded
sentences (`MemoryEvidence.insight`, Phase 4A) and formula-derived
sentences (`ai_summary`/`recommendations`) that currently share one
card with no visual distinction.

**Changed:** the question is not *"should Guest Insight become the one
umbrella concept"* — it should **not**. Collapsing everything into one
label would fix the visual problem while preserving the conceptual
one. A recommendation is not an insight in the same sense a confirmed
guest statement is.

Four distinct epistemic classes, not one:

| Class | Example |
|---|---|
| **Evidence** | "Guest explicitly stated they prefer vegetarian meals." |
| **Derived** | "Guest profile indicates a likely preference for spa services." |
| **Recommendation** | "Consider offering the spa package." |
| **Prediction** | "Estimated likelihood of rebooking: X." |

These can live on the same guest page, even adjacent cards — but they
are not the same semantic category, and the UI needs to say so.

**Decision:** needs a product/design call from you — specifically,
*"what kinds of claims may appear on this surface, and how does the UI
distinguish them?"* That's a design-system foundation question, not a
copy patch, and it's upstream of §3 and §4's fixes (both are really
instances of this same four-class problem).

## 2. Evidence / provenance — confirmed-only stays the boundary

**Kept from round 1:** Phase 4A closed this for its scope. The
inferred track ("Guest Memory: order-pattern evidence track") is
real, deferred, tracked — not started.

**Decision:** **confirmed-only remains the pilot boundary unless
actual pilot evidence creates a reason to reopen it.** Not decided by
this review, not reopened by §1 exposing the distinction.

**Sequencing principle, worth keeping as a standing rule:** don't
create an inference system merely because the UI has a place where an
inference would look good. Build the evidence source first; decide
what product behavior it legitimately supports second. That order
never reverses.

## 3. Actionability vs. affordance integrity

**Kept from round 1:** the Next Best Action card's "Draft upsell →" /
"Send reward →" / "Create offer →" have no click handler — verified,
not hypothesized.

**Changed:** this isn't one question, it's two, and they were being
conflated:

1. *Does the product support the action?* — **No**, today.
2. *Does the UI represent that limitation honestly?* — **Also no.**

That's why "wire them up" was the wrong frame. There are three
legitimate states an affordance can be in:

- **A. Functional action** — "Draft upsell →" opens a real draft
  workflow.
- **B. Recommendation** — "Upsell opportunity," no implication that
  clicking executes anything.
- **C. Disabled / future capability** — clearly presented as
  non-actionable.

The illegitimate state — **D. decorative fake affordance** — is what
exists now.

**Decision:** **remove the false affordance now unless there is
already an agreed, real destination for each action.** Do not create
workflow scope merely to make the arrows clickable — that would be a
premature implementation response dressed as a fix.

## 4. Commercial value — an epistemic-status taxonomy, not a blanket label

**Kept from round 1:** the diagnosis. `return_probability` /
`upsell_probability` / `review_probability` / `churn_risk` are
hand-written weighted sums, never calibrated against outcomes. The
Next Best Action card's `expected_redemption` for the "Win-back offer"
case is a literal hardcoded constant, `0.42`, rendered as "Redemption
42%" with the same visual authority a backtested number would carry.

**Changed:** "label everything as estimated" was too blunt — the word
"estimated" implies a methodology these numbers don't share. A
five-tier vocabulary instead:

| Status | Meaning |
|---|---|
| **Observed** | Directly recorded fact — `lifetime_spend`, `Coupon.redemption_amount`, an accepted `Offer.price`. |
| **Calculated** | Deterministically derived from observed data — no judgment call, just arithmetic. |
| **Heuristic estimate** | Hand-tuned formula, not outcome-calibrated — today's `return_probability` etc. |
| **Illustrative** | Placeholder/demo value, not empirically derived at all — today's `0.42`. |
| **Predicted** | An actual outcome-based model with validation/calibration behind it. Doesn't exist anywhere in this app yet. |

**Standing principle:** a percentage is not automatically a prediction
just because it's expressed as a percentage. A `69%` heuristic score
and a calibrated `69%` probability can look identical on screen while
meaning completely different things operationally — the UI has to
carry the difference, not just the number.

**The `0.42` case specifically:** goes further than "estimated." It
should read as **"Illustrative redemption rate: 42%"**, or the
percentage should come off the operational UI entirely. Softening it
to "estimated" would just make a fabricated number more honestly
fabricated — better than silence, but not the actual fix.

**Decision:** act now. This is the clearest, cheapest, most urgent
product-truth defect in the app today, independent of §1/§2/§3/§5.

## 5. Portable guest memory — plus provenance portability

**Kept from round 1:** not built, not started, green-field. The four
questions (identity resolution, consent, what's actually portable,
business model) stand.

**Added:** a fifth question, **provenance portability**. If a memory
travels from Hotel A to Hotel B, the *evidence* has to travel with the
*claim* — not:

> "Guest prefers vegetarian food."

but something closer to:

> "Guest explicitly stated a vegetarian preference; evidence
> originated at Property A; captured on [date]; verification state:
> confirmed."

Without this, portable memory would quietly undo the evidence
discipline Phase 4A just established — the exact failure mode this
whole review exists to prevent, exported to a second hotel.

**Decision:** split into its own architecture/product document when
prioritized. This is a company-level decision (identity, consent,
business model), not a Phase 4 UI refinement — keep it from gating §1/
§3/§4, which don't depend on it.

## 6. Sequencing

Revised from round 1 — only one change, but it matters:

1. **§4 — act now.** Introduce the epistemic-status taxonomy; fix the
   `0.42` case specifically.
2. **§3 — act now.** Remove the false affordances; don't invent
   workflow scope to justify them.
3. **§1 — define the epistemic model for the guest page.** Not "does
   Guest Insight become the umbrella" — the real decision is *what
   kinds of claims may appear on this surface, and how does the UI
   distinguish them.* Terminology and component design follow from
   that, not the other way around.
4. **§2 — decide, don't default.** Confirmed-only stays the pilot
   boundary unless real pilot evidence says otherwise.
5. **§5 — separate document, own timeline.**

## 7. What this review explicitly resists doing

Three tempting, premature responses — naming them so they don't happen
by accident later:

- **Don't build a prediction model** just because today's percentages
  are weak.
- **Don't build inferred memory** just because §1 exposed the gap
  between evidence and derivation.
- **Don't wire the Next Best Action arrows into speculative workflows**
  just because they're currently dead — remove the false affordance
  instead, unless a real destination already exists.

## 8. Disposition, per section

- **§1 — Needs a product/design decision.** Guest Insight stays
  evidence-grounded; facts, derivations, recommendations, and
  predictions get four distinct treatments, not one bucket.
- **§2 — Keep confirmed-only for the pilot.** Deferred inference stays
  deferred.
- **§3 — Remove false affordances now**, unless a real workflow
  already exists for a given action. No new scope invented to make
  arrows clickable.
- **§4 — Act now on labeling**, using the five-tier taxonomy above.
  `0.42` specifically becomes "Illustrative," not "estimated."
- **§5 — Split into its own architecture/product document,** with
  provenance portability as a required fifth question.
- **Product Truth Principle — adopted as a governing rule** for every
  subsequent ReVisit phase, not a closing observation.

**Still not committed, still not a PR.** This document's job was to
expose the decisions before any implementation starts — that job is
done for §1–§5. What's left is deciding when (not whether) §3 and §4
get scoped into an actual implementation pass, and when §1's
design-system question gets resolved enough to build against.
