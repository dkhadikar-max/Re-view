# Pilot Readiness — Design Document (no code changes; readiness-fix scope only)

Status: **Design only.** No code has been written against this document.
Scope is frozen to the seven readiness gaps identified from inspecting the
actual state of `main` after the Translation Layer merge — nothing else.

**What this document is not:** a feature design. Every item below is a
fix to something that already exists (webhook handling, delivery
tracking, credentials, monitoring, staff workflow, WhatsApp
integration) or a verification plan for something already built. No
new agent, no new guest-facing capability, and no new AI decision
surface is introduced anywhere in this document.

**Explicitly out of scope, by design, sequenced after this document:**
Property-level translation configuration and the WhatsApp
document-based check-in workflow are real, agreed next capabilities —
they are deliberately *not* designed here. The sequence is:

```
Pilot Readiness (this doc) → Property Translation Config →
Check-in / Document Workflow → controlled pilot
```

For check-in specifically: processing government identity documents
carries data-protection and retention obligations that are a **legal
and policy prerequisite**, not an engineering decision this project can
settle on its own. This document records that dependency; it does not
attempt to resolve it.

---

## 0. Non-negotiable objective

**The pilot is not a demonstration that ReVisit has many agents. It is
a controlled test that the existing system can reliably execute the
guest → AI → hotel operational loop.** Every item in this document
exists because it threatens that reliability — a duplicate order, a
silently-dropped reply, an accidental mock-mode pilot, an
unmonitored failure, a staff workflow that only "works" in the API and
never in the screen a real employee looks at. None of these are new
capabilities; all of them are gaps between "the code exists" and "the
loop can be trusted with a real guest."

## 1. Inbound webhook idempotency

**The gap, precisely:** `ingest_inbound_whatsapp` (`messaging.py`)
never checks whether a `Message` with the same `provider_message_id`
already exists before creating a new one and running
`concierge_router.route()`. Meta's Cloud API retries webhook delivery
on timeout or a non-2xx response — a documented, expected behavior,
not an edge case. Today, a retried webhook re-runs the *entire*
pipeline a second time: a second `Message` row, a second (or more)
`ActionEvent`, and — depending on what the guest's message triggered —
a second `Order`, a second staff `Task`, or a second guest-memory note
appended via `guest.notes`.

**Also true today:** `Message.provider_message_id` has no uniqueness
constraint at the schema level (`entities.py` — nullable `String(128)`,
no unique index, no composite index). A dedup check has to be added
deliberately; it isn't implicitly enforced by the database.

**What this document requires (design intent, not code):**
- Before creating the inbound `Message`, check for an existing
  `Message` with the same `provider_message_id` when one is present
  (some inbound event shapes may lack it — the check must be
  conditional, not assumed always-present) and short-circuit: return
  the existing message, do not re-invoke the Concierge Router, do not
  re-append guest-memory notes.
- Decide explicitly whether the dedup key is `provider_message_id`
  alone (Meta's IDs are globally unique per WABA) or the pair
  `(tenant_id, provider_message_id)`. Given ReVisit's platform-level
  WABA (`CONCIERGE.md` §3 — one ReVisit-owned WABA sends through many
  properties' numbers), the safer default is the pair, so a dedup bug
  can never cross a tenant boundary even in theory.
- Whatever index is added must not weaken today's existing tenant
  isolation guarantees — the dedup check itself must be tenant-scoped
  in its query, not a global lookup that could leak existence
  information across tenants.
- This is a small, independently testable change: one new query before
  the existing `Message(...)` construction, one new test proving a
  replayed webhook produces exactly one `ActionEvent`/`Order`/`Task`
  where a fresh one would.

## 2. Outbound delivery reliability

**What already exists and is sound:** `Message.status`
(`draft`/`pending_approval`/`queued`/`sent`/`delivered`/`failed`) and
`MESSAGE_TRANSITIONS` (`state_machine.py`) already model delivery
state explicitly. `deliver_message` already transitions to `failed` on
any exception and re-raises. Translation Layer's constraint 7
(`TRANSLATION_LAYER.md` §2) already guarantees translation failure
never touches the already-committed `ActionEvent`/`Order` — only the
new outbound `Message` is marked `failed`. This part of the
architecture does not need to change.

**The gap:** a `failed` message today just stays `failed`. Nothing
retries it — `process_due_messages` only ever picks up `queued`
messages, never `failed` ones — and nothing surfaces it to a human.
The `MESSAGE_TRANSITIONS` table already permits `failed -> draft` and
`failed -> queued`, so the state machine supports a retry path; nothing
currently drives it.

**What this document requires:**
- An explicit, minimal retry mechanism appropriate to pilot scale (1-2
  hotels): a bounded number of automatic retry attempts (e.g. via the
  existing `process_due_messages` sweep, extended to also pick up
  `failed` messages below a retry-count threshold), not a general
  message-queue redesign.
- A hard requirement that **no outbound failure is silent**: at
  minimum, a `failed` message that exhausts its retries must be
  queryable/visible (feeds directly into §4's monitoring, not a
  separate mechanism).
- No change to the translation-failure boundary itself — this section
  is about what happens to a `Message` already correctly marked
  `failed`, not about re-opening constraint 7.

## 3. Production credentials / go-live

**What already exists:** `.env.example` ships `USE_MOCK_AI=true`, an
empty `OPENAI_API_KEY`, and an empty `WHATSAPP_ACCESS_TOKEN`.
`AIGateway.configured` and `TranslationClient.configured` both
correctly gate on `not settings.use_mock_ai` *and* key presence — the
mock/live convention itself is sound and doesn't need redesigning.

**The gap:** nothing today *prevents* a pilot from silently running in
mock mode. If `USE_MOCK_AI` is left `true` (the shipped default) in a
pilot's production environment, Translation Layer runs in pure
passthrough (a non-English guest receives their own message echoed
back untranslated) and WhatsApp sends never leave the mock client (no
message ever reaches a real phone) — with no error, no warning, and
identical-looking success logs to a correctly configured pilot.

**What this document requires:**
- A go-live checklist, not just documentation: `OPENAI_API_KEY` set,
  `USE_MOCK_AI=false`, `WHATSAPP_ACCESS_TOKEN`/`WHATSAPP_APP_SECRET`/
  `WHATSAPP_VERIFY_TOKEN` set, and every pilot property's
  `Property.whatsapp_phone_number_id` populated.
- A **boot-time guard**, following the same convention already
  established in `config.py`'s
  `reject_ephemeral_sqlite_in_production` validator: refuse to start
  (or at minimum, refuse to serve guest-facing WhatsApp/translation
  traffic) when `environment` indicates a real deployment and
  `use_mock_ai` is still `true`. This turns "someone forgot to flip a
  flag" from a silent pilot failure into a startup error.
- Confirm (spot-check, not a redesign) that `WhatsAppCloudClient` and
  `TranslationClient` never log the token/API key itself — both
  currently log `phone_number_id`/model name/message metadata, not
  credentials, but this should be explicitly verified rather than
  assumed as part of go-live sign-off.
- Per-property configuration is explicitly limited to what already
  exists (`Property.whatsapp_phone_number_id`) — property-level
  *translation* configuration is the next document, not this one.

## 4. Monitoring and alerting

**Explicit non-goal:** a full observability platform. At pilot scale
(1-2 hotels), the requirement is *basic operational visibility* —
someone can find out, without reading raw server logs, that something
needs attention.

**What this document requires**, as queryable/reportable conditions
(mechanism — dashboard, scheduled report, admin endpoint — is an
implementation detail to be decided in the readiness PR, not this
document):
- Failed inbound processing: any turn where `TranslationError` or
  `ContextBuilderError` caused the Router to be skipped (both already
  logged via `logger.exception` in `messaging.py` — the gap is
  aggregation/visibility, not the logging itself).
- Failed outbound delivery: `Message` rows in `failed` status,
  cross-referenced with §2's retry mechanism (only worth alerting on
  *exhausted* retries, not every transient failure).
- Translation failures specifically (a subset of the above, but worth
  distinguishing operationally from a WhatsApp API outage — different
  root cause, different fix).
- Webhook duplication: how often §1's dedup check actually fires — a
  spike would indicate a Meta-side delivery problem worth knowing
  about even though the system is handling it correctly.
- Staff Task failures/stale tasks: `Task` rows in `open` status beyond
  a reasonable threshold (e.g. 24h) — see §5 for why this connects
  directly to the evidence-chain gap found there.

## 5. Staff Task end-to-end verification

**The verification path:** guest action → `Task` created → staff sees
it in the actual frontend (not just via `GET /tasks`) → staff completes
it via the actual frontend button (not just `POST
/tasks/{id}/complete`) → completion is durably recorded → the
correlation/evidence chain survives the entire flow.

**A concrete gap found while writing this document:**
`complete_task` (`routes.py`) sets `Task.status = TaskStatus.done` and
commits — it does not create an `ActionEvent`. This means today's
Action Ledger evidence chain for an order is
`ORDER_PROPOSED → ORDER_CONFIRMED → TASK_CREATED` and then **nothing**
— staff actually completing the work, the very last step of the
guest → AI → hotel loop this pilot exists to observe, leaves no
ledger record at all. `ActorType.staff` already exists in the taxonomy
(`CONCIERGE.md`'s action_type table) specifically for this kind of
event and is currently unused by any code path.

**What this document requires:**
- Manual E2E verification using the existing frontend: place a real
  order (or trigger a real escalation) through the actual guest-facing
  channel, confirm the `Task` appears where a hotel employee would
  actually look, confirm completing it there updates state correctly.
- A `TASK_COMPLETED` (or equivalently named, consistent with the
  frozen v1 taxonomy in `CONCIERGE.md`) `ActionEvent`, logged with
  `actor=ActorType.staff` and the same `correlation_id` as the
  originating chain, so the evidence trail for "did the hotel actually
  do the thing" exists at all. This is a small, contained addition to
  `complete_task` — not a workflow redesign.
- Confirm the completed chain's `correlation_id` genuinely ties every
  event together end-to-end (`ORDER_PROPOSED`/`ORDER_CONFIRMED`/
  `TASK_CREATED`/`TASK_COMPLETED` sharing one id) — this is exactly the
  kind of check the PR #31 architectural review already applied to the
  proposal→confirmation half of the chain; this section extends it to
  cover the execution half for the first time.

## 6. Real WhatsApp verification

Everything built so far — all 333+ backend tests — has been verified
against the mock `WhatsAppCloudClient` and a stub `TranslationClient`.
None of it has round-tripped through Meta's actual Cloud API or a real
LLM translation call. This section is a verification plan, not new
functionality:

- Using a Meta test/sandbox WhatsApp number (never real hotel traffic
  for this step): a real inbound message round trip, and a real
  outbound delivery round trip.
- Deliberately re-sending the same webhook payload (Meta's own webhook
  test tool, or a manual re-POST) to confirm §1's dedup behavior holds
  against the real payload shape, not just the shape assumed in tests.
- A real non-English inbound message, with a real `OPENAI_API_KEY`
  configured (`USE_MOCK_AI=false`), to observe actual detection/
  translation quality for the first time — this has never been
  measured, only unit-tested against a deterministic stub.
- A deliberately forced translation failure (e.g. a temporarily invalid
  API key) against the *live* pipeline, to confirm constraint 7's
  behavior — no untranslated fallback sent, `ActionEvent`/`Order`
  unaffected, message marked `failed` — holds outside the test suite,
  not only inside it.

## 7. Pilot acceptance criteria

**Updated post-implementation.** §1–§5 shipped as PRs #37–#41; the
shared-WABA-vs-BYO architecture question raised while attempting §6
was resolved and implemented as PRs #42–#43
(`WHATSAPP_PLATFORM_ARCHITECTURE.md`). This section now reflects that
closed-out state rather than the pre-implementation plan — the
original must-pass list named a live §6 round trip as a blocker to
pilot start; it no longer is, for the reason below.

**Engineering pilot readiness: PASS.** Eight gates, each verified
against merged code and CI, not asserted:

1. **Production boot** — real integrations required; mock mode cannot
   masquerade as production (PR #39, PR #43).
2. **Connected-property isolation** — WhatsApp traffic resolves to the
   correct `Property`/tenant via `whatsapp_phone_number_id`
   (CONCIERGE.md §3).
3. **Duplicate webhook protection** — the same `provider_message_id`
   cannot execute the concierge pipeline twice (PR #37).
4. **Inbound processing** — the guest's original message is preserved
   unmodified, normalized when required, and reaches the existing
   pipeline correctly (Translation Layer, PR #37).
5. **Outbound delivery** — replies enter the delivery state machine
   with bounded retry; failures remain observable, not silent
   (PR #38, PR #40).
6. **Evidence chain** — decisions, orders, tasks, and task completion
   share one `correlation_id` end-to-end; prior ledger events are
   never mutated, only appended to (PR #41).
7. **Staff execution** — a real staff user can see and complete the
   resulting `Task` through the actual frontend, not only the API
   (PR #41).
8. **Safety boundaries** — no autonomous substitutions, fabricated
   menu data, allergen-safety claims, payment execution, or unintended
   memory mutation. Not one gate but distributed by design: the
   Escalation Filter's hard-safety patterns, the Context Builder's
   "never invent" discipline on the Revenue/Menu agents, no PMS
   integration (so nothing executes beyond a staff `Task`), and the
   Memory Manager's confidence-band gating before any guest-profile
   mutation.

**Operational pilot validation: pending the first real property.**
§6's live round trip was never an engineering gap — the code has
always been ready to speak to Meta's real Cloud API and a real LLM
translation call, exactly as built and tested against mocks/stubs.
What was missing was a real hotel's WABA connection, which is
correctly an onboarding activity, not a pre-pilot engineering
deliverable, and must not be simulated with a developer-owned
WhatsApp account. §6 is reframed as the **operational validation
checklist run once during the first controlled hotel's onboarding**,
not a condition of shipping engineering readiness:

Connect the hotel's WABA → assign `Property.whatsapp_phone_number_id`
→ mark the property `connected` (`WHATSAPP_PLATFORM_ARCHITECTURE.md`
§3) → send controlled messages (inbound English, inbound non-English,
FAQ, service/order request, confirmation) → verify inbound/outbound
behavior → verify ledger correlation end-to-end → complete the
resulting staff Task → resend the same webhook/message → verify
deduplication holds against the real payload shape.

Until that sequence runs against a real property, the system is
engineering-complete but not yet pilot-validated — a factual,
operational statement, not an open engineering question.

**Must-fix, can land alongside pilot start rather than strictly block
it:** none remaining — §2 (outbound retry) and §4 (monitoring) both
shipped as PRs #38/#40 and are part of the engineering-readiness PASS
above, not open items.

**Deferred (unchanged from prior session decisions, restated for
completeness):** payments, POS/kitchen integration, dynamic pricing,
autonomous substitutions, response caching, WhatsApp media/voice
support, order cancellation-after-confirmation, Guest Memory
pattern-evidence track, any additional concierge agent, property-level
translation configuration, the check-in/document workflow, and
per-property (BYO) WhatsApp credentials
(`WHATSAPP_PLATFORM_ARCHITECTURE.md` §0) — the check-in/document and
translation-config items are real, agreed next steps, sequenced
strictly after a real pilot's evidence, not folded into this phase.

**Standing rule, unchanged:** no new agent capability is added simply
because it is technically possible. Feature development on this
platform stops here. The next move is one real hotel, one controlled
property, one end-to-end operational run — the objective shifts from
building capability to measuring whether the capability works in
reality.

## 8. What happens after this document

Once reviewed and frozen, implementation should be scoped as a small
number of narrow, independently-testable PRs — not one large change —
consistent with every prior PR in this project's history. A plausible
split (to be confirmed at implementation time, not fixed here):
idempotency (§1) as one PR, delivery-retry + monitoring (§2 + §4) as a
second, the go-live guard (§3) as a third (small enough it could ride
with either), and staff-Task evidence (§5) as its own PR given it
touches the Action Ledger taxonomy. §6 is verification work against a
real WhatsApp sandbox, not a PR at all.

No implementation begins until this document is explicitly approved.
