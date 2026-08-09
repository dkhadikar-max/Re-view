# Translation Layer — Design Document (frozen contract, no implementation yet)

Status: **Design only.** No code has been written against this document.
This doc exists to freeze the I/O-boundary contract and the seven
constraints agreed on before any implementation PR is opened, per the
same plan-first discipline as `CONCIERGE.md` and `MENU_ORDERING.md`.
(Originally frozen with six constraints in the initial design PR; a
seventh — the outbound translation-failure guarantee — was added as a
follow-up before implementation began, since it was recognized as an
architectural invariant rather than an implementation detail.)

Roadmap position: this is priority #8, the final new capability before
Pilot Readiness (#9) and the strategic stop (#10). After this design is
approved, translation implementation is the last engineering step
before ReVisit stops adding agents and prepares for real hotel usage.

---

## 0. Non-negotiable design principle

**Translation is an I/O normalization layer, not an intelligence
layer.** It sits at the two edges of the Concierge pipeline — inbound
guest message and outbound guest-facing response — and touches nothing
in between. Every agent, the Router, the Escalation Filter, the
Context Builder, the Conversation Manager, and the Action Ledger
continue operating exactly as they do today, entirely in English, with
no awareness that translation exists. If a design or implementation
choice would require any of those components to change behavior based
on the guest's language, that choice is out of scope for this layer —
it belongs to a future decision, not this one.

This mirrors the same discipline `MENU_ORDERING.md` §12 already
established for Ordering Agent: the safest guarantee is often the one
achieved by a component *not* being able to touch something, not by a
runtime check that trusts it not to.

## 1. The boundary

```
Guest (any language)
        │
        ▼
┌─────────────────────┐
│ 1. Detect language   │  language tag stored, not guessed per-turn
│ 2. Normalize inbound │  translate guest text → English
│    text to English   │  ORIGINAL TEXT PRESERVED UNCHANGED (§4)
└─────────┬────────────┘
          │  (English text, from here on indistinguishable from an
          │   English-speaking guest's message)
          ▼
┌──────────────────────────────────────────────────────────┐
│         Existing Concierge pipeline — UNCHANGED           │
│ Escalation Filter → Conversation Manager (find_active) →  │
│ Context Builder → Intent Classifier → Agent → Action      │
│ Logger → Conversation Manager                              │
└─────────┬────────────────────────────────────────────────┘
          │  (English response text + structured metadata)
          ▼
┌─────────────────────┐
│ 3. Translate final   │  translate English response → guest's
│    response only     │  detected language
└─────────┬────────────┘
          │
          ▼
Guest (their own language)
```

Two translation calls per guest turn, both at the edges: one in, one
out. Nothing in the middle is touched, extended, or made
language-aware.

## 2. The seven frozen constraints

These were agreed on explicitly before this document was written and
are non-negotiable for the implementation PR:

1. **No translation-based intent reinterpretation.** The normalized
   English text is handed to the Intent Classifier exactly as any
   other English message would be. Translation does not get its own
   opinion about what the guest meant — it only converts language, and
   whatever ambiguity or mistranslation that introduces is inherited by
   the existing deterministic pipeline, not corrected by a smarter
   translation step.
2. **No changes to the deterministic Router/Agents.** `escalation_filter.py`,
   `conversation_manager.py`, `context_builder.py`, `intent_classifier.py`,
   and every agent (`faq_agent`, `revenue_agent`, `ordering_agent`,
   `guest_memory_agent`) stay exactly as they are. None of them import
   or call anything translation-related, directly or indirectly.
3. **Structured data stays canonical.** Prices, currencies, menu item
   names, `action_type` values, confidence scores, and every Action
   Ledger field are stored and compared in their original
   (English/numeric/enum) form, never translated. A guest sees a
   translated *sentence* describing "Chicken Biryani, ₹450" — the
   underlying `OrderItem.name`/`price`/`currency` and the
   `ActionEvent.action_type` value `ORDER_CONFIRMED` are untouched by
   translation at every layer beneath the final rendered reply.
4. **Original guest text remains available for audit/evidence.** The
   guest's message in their own language is preserved and retrievable
   — never overwritten by, or discarded in favor of, its English
   normalization. Both versions exist; the English version is what the
   pipeline reasons over, the original is what the evidence chain
   (Argus) and any human review sees as "what the guest actually said."
5. **No autonomous memory creation from translated text.** Guest
   Memory Agent's existing two tracks (explicit-statement and
   pattern-evidence, `MENU_ORDERING.md` §9) are not extended with a
   third "inferred during translation" path. If normalization is
   imperfect, the failure mode is a wrong answer to that one message,
   not a wrong permanent memory.
6. **Translation must not silently alter an order, confirmation,
   dietary fact, or other structured action.** Confirmation matching
   (`conversation_manager.py`'s yes/no resolution), cart contents
   (`PendingAction.payload`), and any guest-stated dietary/allergy
   information are read from the *normalized English* text the same
   way they always have been — translation has exactly one chance to
   get "yes" right, the same as English guests already get exactly one
   chance to say "yes" clearly. No separate translation-aware
   leniency, no retry-with-different-phrasing logic, no confidence
   threshold specific to translated messages. If normalization
   produces an unclear result, the existing "unclear reply stays
   pending" and escalation paths (already built, §7.4 of
   `MENU_ORDERING.md`) handle it exactly as they handle any unclear
   English message today.
7. **Translation failure must never cause the system to invent,
   partially execute, or silently alter a guest action.** This is
   deliberately as strong a guarantee as constraint 6, and covers the
   opposite direction of the pipeline: outbound translation failing
   after an action has already been decided and logged in English.
   Concretely, when the final response translation call fails:
   - The `ActionEvent` already written by Action Logger (§5) is
     unchanged — no retraction, no edit, no re-logging.
   - Any `Order`, `PendingAction`, or confirmation state already
     created or updated by that turn is unchanged — a translation
     failure on the way *out* never rolls back a decision that was
     already correctly made on the way *in* and through the pipeline.
   - There is no reinterpretation or retry with looser semantics —
     the system does not fall back to a "best guess" translation, a
     partial translation, or an untranslated-but-silently-sent English
     message dressed up as a fix. The action's canonical state is
     already correct and auditable; only its *delivery* to the guest
     failed.
   - Delivery failure is handled the same way any other outbound
     WhatsApp send failure already is — the existing operational
     retry/alerting path, not a translation-specific escape hatch.
   In short: translation sits strictly downstream of every decision
   the pipeline makes. A failure in that downstream step can only ever
   cause a guest to not receive a (translated) message — it can never
   cause the system to have decided, recorded, or executed something
   different than what the English pipeline already decided.

## 3. What "detect/normalize" means concretely

- **Language detection** happens once per inbound message (not once
  per guest — a returning guest could plausibly write in a different
  language turn to turn, e.g. switching to English mid-conversation).
  Detected language is stored alongside the message, not just used
  transiently, so the outbound leg (§4) knows what to translate back
  into without re-detecting.
- **Normalization** is a translation call: guest's detected language →
  English. The output replaces nothing — it is a new field alongside
  the original, per constraint 4.
- English-language messages pass through both legs as a no-op (no
  translation call made, or a call that's a deterministic
  identity/skip) — this is not a "translate everything through a
  pivot language" design; if the guest is already writing English nothing
  changes about their experience or latency today.

## 4. Where the original text lives

The inbound message record gains a `detected_language` field and an
`original_text`/`normalized_text` pair (naming TBD at implementation
time), rather than a single `body` field being mutated in place.
Every place that currently reads "the guest's message" for
Escalation Filter, Intent Classifier, agent matching, or confirmation
resolution reads `normalized_text`. Every place that currently reads
"the guest's message" for the Action Ledger's `input_summary` or any
future audit/evidence export reads `original_text`. This is a
one-time decision about which field feeds which consumer — not a
runtime branch anywhere in the pipeline.

## 5. Where response translation happens

The Concierge pipeline's final English response (whatever an agent or
the Conversation Manager produced) is translated to the guest's
`detected_language` as the very last step before the outbound WhatsApp
send — after Action Logger has already recorded the English decision
and metadata. Translation of the outbound leg never runs before
logging, so the ledger always contains the same English record
regardless of guest language.

## 6. Explicit non-goals (do not build these under this design)

- No multilingual expansion of any agent's regex/keyword patterns —
  every pattern in `escalation_filter.py`, `ordering_agent.py`,
  `revenue_agent.py`, `guest_memory_agent.py`, and `intent_classifier.py`
  stays English-only, forever, under this design. Multilingual pattern
  matching (if ever wanted) is a different, much larger decision than
  this document authorizes.
- No LLM-driven reinterpretation of intent "to compensate" for
  imperfect translation.
- No caching or reuse of a guest's detected language across properties
  or tenants — detection is per-conversation, scoped the same way
  everything else in this codebase is tenant-scoped.
- No translation of stored `MenuItem`, `Property`, `KnowledgeBase`, or
  any hotel-configured content at write time — the hotel's own data
  stays in whatever language the hotel entered it; only the
  *guest-facing reply sentence* gets translated, not the underlying
  facts being described.
- No voice/audio translation — text only, matching WhatsApp inbound
  parsing's existing text-only scope (`CONCIERGE.md` §2).

## 7. Open questions for the implementation PR (not resolved here)

- Which translation provider/API to use.
- Exact field names and migration shape for `detected_language` /
  `original_text` / `normalized_text`.
- Whether detection runs synchronously inline or is itself a small
  deterministic step before Escalation Filter — either is compatible
  with this contract as long as Escalation Filter still receives
  normalized English.

Inbound normalization failure (translation-to-English fails before the
guest's message reaches the pipeline at all) and outbound delivery
mechanics both resolve to existing behavior: an inbound failure means
the pipeline never runs for that message, which is exactly the "when
in doubt, escalate" default per §0 — not a new decision this document
needs to make. Outbound failure is fully resolved by constraint 7
above, not left open.

These are implementation details deliberately left open here — this
document's job is only to freeze the boundary and the seven constraints
above, not to pre-decide every line of code.

## 8. Implementation sequence (not started — do not build ahead of this)

1. Inbound normalization: detect language, translate to English,
   store both texts.
2. Wire normalized text into the existing pipeline entry point —
   zero changes inside the pipeline itself.
3. Outbound translation: translate the final English response back,
   after Action Logger has already run.
4. Tests proving the seven constraints hold: an agent given a
   translated message never sees anything but English; Action Ledger
   fields stay English/canonical regardless of guest language;
   original text survives round-trip; an unclear confirmation in a
   non-English message hits the same "stays pending" / escalation path
   as an unclear English one; and a simulated outbound translation
   failure leaves the already-logged `ActionEvent`/`Order`/confirmation
   state completely unchanged, triggering only the existing delivery
   retry/alert path.

No implementation begins until this document is explicitly approved.
