# WhatsApp Conversation Platform + AI Concierge — Design Document

Status: Draft, not yet implemented. No code has been written against this
document, per the same discipline PDF_IMPORT.md and EMAIL_IMPORT.md were
built under — design first, review gate, then implementation.

Scope: this doc covers Phase 1 (WhatsApp Infrastructure, closing the
real gaps) and Phase 2 (AI Concierge), including the Knowledge Base data
model Phase 2 depends on. Guest Memory (Phase 4) is **not** redesigned
here — it's already substantially built (§2) and this doc treats it as
an existing dependency to read from and write to. Automation Engine
trigger wiring (Phase 5) is named as a deliberate follow-on (§9), not
detailed here, because it's mostly configuring the existing
`Workflow`/`WorkflowRun` engine against events this doc's conversations
will emit — it doesn't need new engine code to be designed first.

---

## 1. Why this needs a design pass first — and why more than PDF or Email did

PDF and Email Import's worst-case failure is a wrong or skipped
*import* — bad, but caught by a human on a review screen before
anything reaches a guest, and reversible (the reservation just doesn't
exist, or gets corrected). The AI Concierge's worst-case failure is a
wrong answer **sent directly to a real hotel guest**, with no review
screen in between by design — the entire point of a concierge is
answering in real time. That is categorically higher stakes than
anything shipped so far in this product, and it's the reason §5
(escalation rules) is the load-bearing section of this document, the
way §3 (trust model) was for Email Import and §4 (confidence) was for
PDF Import.

Concretely, three failure modes that don't exist anywhere else in
ReVisit today:
- **A guest asks something and the concierge invents an answer** not
  actually true for that hotel (wrong pool hours, wrong Wi-Fi password,
  a room-service item that doesn't exist).
- **A guest asks something the concierge should never answer
  autonomously** (allergy/medical/safety questions, a complaint, a
  request that implies distress) and it tries anyway instead of routing
  to a human.
- **A guest is upsold something inappropriately** (a spa offer sent to
  someone who just complained about noise) because the "decide the next
  best action" logic that already exists for outbound campaigns
  (`ai_orchestrator.py`) wasn't built for a live back-and-forth
  conversation and doesn't have a concept of "we're mid-conversation,
  don't also fire a scheduled upsell right now."

## 2. What already exists (audit, so this doc doesn't redesign it)

| Capability | Status | Where |
|---|---|---|
| WhatsApp outbound send (mock + live) | ✅ Built | `app/integrations/whatsapp.py` |
| Webhook signature verification (HMAC) | ✅ Built | `whatsapp.py: verify_signature` |
| Webhook challenge verification | ✅ Built | `whatsapp.py: verify_webhook_challenge` |
| Inbound text message parsing | ✅ Built (text only) | `whatsapp.py: parse_webhook` |
| Inbound message storage | ✅ Built | `messaging.py: ingest_inbound_whatsapp` |
| Multi-tenant inbound routing | ❌ Not built | `integrations.py`'s webhook hardcodes `tenant_id = "demo-hotel"` — see §4 |
| Media (image/document/audio) inbound | ❌ Not built | parser only handles `msg.type == "text"` |
| Message templates (Meta's 24h-window rule) | ❌ Not built | no template model/config exists |
| Guest Memory (preferences, complaints, upsell history) | ✅ Largely built | `Guest` model already has `preferred_room`, `dietary_preferences`, `birthday`/`anniversary`, `complaint_history`, `upsell_acceptance`, `previous_reviews` |
| Automation trigger engine | ✅ Foundation built | `Workflow`/`WorkflowRun` already support arbitrary `trigger` + step sequences (`wait`/`ai`/`template`/`send`/`notify`) |
| "Decide next action" AI (outbound campaigns) | ✅ Built, different shape | `ai_orchestrator.py` — one-shot decision (Welcome/Upsell/ReviewRequest/None), not a conversational loop; reused for triggered sends, not replaces by this doc |

## 3. Multi-tenant WhatsApp routing — the first real gap to close

This matters more than it looks like, because it's the one piece of
Phase 1 that changes onboarding friction directly (the GTM thesis this
whole roadmap is built around).

**The problem**: `config.py` has exactly one global
`whatsapp_phone_number_id`/`whatsapp_access_token`/`whatsapp_app_secret`
— the entire integration is architected single-tenant today. The
current inbound webhook doesn't even try to route by tenant; it
hardcodes `"demo-hotel"`.

**Two ways to fix it, and which one this doc recommends:**

- **Each hotel gets its own WhatsApp number.** Most intuitive for
  guests ("message the hotel's WhatsApp"), but adds real onboarding
  friction per hotel (a phone number, possibly Meta verification steps)
  — works against the 15-minute setup wizard goal.
- **One ReVisit-owned WABA (WhatsApp Business Account) hosts a distinct
  phone number per tenant.** A single Meta Business/WABA can host
  multiple phone numbers; Meta's inbound webhook payload includes
  `value.metadata.phone_number_id` on every message — **this field
  already exists in every webhook Meta sends and the current
  `parse_webhook` silently discards it.** Routing inbound messages by
  looking up which tenant owns the `phone_number_id` the message
  arrived at is the standard multi-tenant WhatsApp SaaS pattern, and it
  requires zero new Meta-side complexity — just capturing a field
  that's already there and storing a `Property.whatsapp_phone_number_id`
  (or a new dedicated column) instead of reading one global setting.

**Recommended: the second option.** It's a schema change (one new
column) plus reading `value["metadata"]["phone_number_id"]` in
`parse_webhook` instead of discarding it, not new Meta-side
infrastructure — and it doesn't add a single step to hotel onboarding
once ReVisit's WABA itself is set up (a one-time platform setup, not a
per-hotel one). Provisioning each tenant's actual phone number under
that WABA is still a real operational step (§10 open question) — this
section only resolves the *routing* architecture, not who does the
provisioning.

## 4. Conversation architecture

```
Inbound WhatsApp message
        │
        ▼
Resolve tenant via phone_number_id (§3)
        │
        ▼
Resolve guest via from-phone, scoped to that tenant
(unknown guest at a known tenant's number → §6)
        │
        ▼
Load conversation context:
  - Guest Memory (existing Guest fields — §2)
  - Active/recent Reservation for this guest
  - Knowledge Base for this guest's property (§5)
  - Last N messages in this conversation (new: conversation history)
        │
        ▼
Escalation check FIRST, before any answer is generated (§6) —
safety/medical/complaint/distress signals never reach the
answer-generation step at all
        │
        ▼
AI Concierge reply (structured, same contract discipline as
AIGateway elsewhere — see §7): answer | recommend | offer |
request-review | escalate
        │
        ▼
   ┌────┴─────┐
   │          │
escalate   everything else
   │          │
   ▼          ▼
Notify a    Send via WhatsApp,
human       log to conversation
(Task/       history, update
Notification) Guest Memory if the
             conversation revealed
             something worth
             remembering (§2)
```

This is a genuinely new loop — nothing in `ai_orchestrator.py` runs
this shape today (it decides once, for an outbound campaign; this
answers repeatedly, in a live back-and-forth, with an escalation gate
in front of every single turn).

## 5. Knowledge Base — v1 is structured data, not vector retrieval

Per this app's established "zero-cost first" philosophy
(`zero_cost_agent.py`, and the same reasoning behind PDF's
digital-text-before-OCR default): **v1 knowledge base is structured
per-property fields the concierge looks up directly, not a vector
database with embeddings and semantic search.** A hotel's Wi-Fi
password, breakfast hours, and pool hours are a handful of fixed facts,
not a large enough corpus to need retrieval-augmented generation — and
a wrong retrieval from an over-engineered RAG system is exactly the
kind of failure §1 is trying to avoid. Structured fields also make it
trivial to answer "I don't know that" honestly (the field is empty)
instead of the model guessing from a nearest-neighbor match that
happened to be irrelevant.

Proposed shape (new `PropertyKnowledgeBase` entity, one row per
property, mirrors how `Property` itself already holds one row per
property rather than a separate table per field group):

| Group | Fields |
|---|---|
| Practical info | wifi_password, checkin_time, checkout_time, parking_info, pool_hours, gym_hours, spa_hours |
| House rules | house_rules (free text) |
| Local recommendations | restaurants, cafes, attractions, transport (each a short list — name + one-line description, not full reviews) |
| Services & pricing | services (name + price + how to request), room_service_hours |
| Emergency | emergency_contacts |

If a field is empty, the concierge says so and escalates rather than
guessing — same "Ready to Import / Needs Review" binary-honesty
convention this app already uses everywhere else, applied here as
"Answered from Knowledge Base / Escalated because the Knowledge Base
doesn't have this."

**Revisit vector/RAG only if**: a hotel's local-recommendations content
grows large enough that structured lookup genuinely can't cover it
(e.g. a city guide with hundreds of entries) — not before real usage
shows that's needed.

## 6. Escalation rules — the section that matters most

The concierge **never** answers, and always creates a human-visible
Task/Notification instead, when a message matches any of:

- Medical, allergy, or safety-related content of any kind (this app
  gives zero medical advice, full stop — not "gives cautious medical
  advice")
- A complaint, or language suggesting the guest is upset/distressed
- A request the Knowledge Base doesn't have an answer for and can't
  honestly answer from Guest Memory either
- A request implying a financial transaction beyond an existing Offer
  flow (e.g. "can you refund me") — payments already have their own
  reviewed flow (`stripe_payments.py`, `create_payment_link`); the
  concierge should route into that, not improvise pricing/refund logic
- Anything the guest explicitly asks to speak to a human about

This list is a starting point, not exhaustive — it should be tuned
against real pilot conversations (§9's link to the "customer feedback
drives the roadmap" principle), but it starts wide/conservative
(escalate more than strictly necessary) and narrows only once real
transcripts show a category is safe to auto-answer, never the other
direction.

## 7. AI provider, cost, and fallback

Same `AIGateway` contract as PDF/Email (structured-JSON-only,
Pydantic-validated, mock/heuristic fallback when unconfigured) — new
system prompt, same discipline. Unlike PDF's AI Parser, a
concierge reply genuinely needs a real LLM call most of the time (this
isn't a case where a regex heuristic can substitute the way PDF's
mock-mode fallback does for structured field extraction) — the mock/
no-API-key fallback for v1 should be a fixed "Thanks for reaching out —
a member of our team will get back to you shortly" template plus an
automatic escalation, not an attempt at heuristic conversation. Being
honest about "no AI configured" beats a fake canned-answer bot.

## 8. Review-flow detection

"Detect satisfied guests, ask for a review" reuses the existing review-
request machinery (`Message.message_type == "review_request"`, already
counted in `build_import_summary`'s `reviews_scheduled` metric) — the
new part is *triggering* it from conversation sentiment rather than
only from the existing post-checkout schedule. Concretely: if a
guest's message expresses clear satisfaction (not inferred from
silence — an explicit positive signal), queue the existing review-
request flow immediately rather than waiting for the scheduled trigger.
This is an additional trigger into an existing flow, not a new one.

## 9. Automation Engine — deliberately not detailed here

`Workflow`/`WorkflowRun` already support arbitrary triggers and step
sequences (§2). Wiring pre-arrival/check-in/mid-stay/checkout/post-
checkout triggers to fire from the event bus is real work, but it's
*configuration and event-wiring* against an engine that already exists
— it doesn't have unresolved design risk the way §3/§5/§6 do, and
doesn't need its own document. It becomes a build task once this
doc's conversation loop exists to be triggered.

## 10. Explicitly out of scope for v1

- **Voice/audio messages** — text only, same as PDF started
  digital-text-only before considering OCR.
- **Vector/RAG knowledge base** — see §5.
- **Multi-language concierge replies beyond what the guest writes in**
  — reply in the guest's language if the model can, don't build a
  separate translation layer.
- **Fully autonomous booking modifications** (guest asks to change
  check-out date via chat and it just happens) — anything that mutates
  a reservation goes through existing reviewed flows, not directly from
  a chat reply.
- **Per-hotel WhatsApp number self-service provisioning** — see §10
  open questions; v1 assumes ReVisit provisions numbers, not a hotel
  self-serve flow.

## 11. Open questions before implementation starts

1. **Who provisions each tenant's WhatsApp phone number under
   ReVisit's WABA, and how** — a one-time Meta Business step this
   assistant can't perform. Affects how real the "15-minute setup
   wizard" promise can be for the WhatsApp channel specifically (import
   sources don't have this constraint; WhatsApp does).
2. **Escalation list in §6 — confirm or adjust before any code is
   written.** This is the one section where getting the default wrong
   in the conservative direction (escalating something that could have
   been auto-answered) costs a little response-time; getting it wrong
   in the permissive direction (auto-answering something that should
   have escalated) costs guest trust or worse. Needs explicit sign-off,
   not an assumption.
3. **Message template strategy for Meta's 24-hour window rule** —
   outside 24 hours since the guest's last message, WhatsApp requires a
   pre-approved template for any hotel-initiated message (the
   automation triggers in §9 will hit this immediately for pre-arrival/
   post-checkout messages, which by definition happen outside an active
   conversation window). Needs a decision on which templates to submit
   for Meta approval and how far in advance, since template approval
   isn't instant.
