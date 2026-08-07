# WhatsApp Conversation Platform + AI Concierge — Design Document

Status: Draft, not yet implemented. No code has been written against this
document, per the same discipline PDF_IMPORT.md and EMAIL_IMPORT.md were
built under — design first, review gate, then implementation.

Scope: this doc covers Phase 1 (WhatsApp Infrastructure, closing the
real gaps) and Phase 2 (AI Concierge), including the Knowledge Base data
model Phase 2 depends on. Guest Memory (Phase 4) is **not** redesigned
here — it's already substantially built (§2) and this doc treats it as
an existing dependency, now formalized as one of the four agents (§5).
Automation Engine trigger wiring (Phase 5) is named as a deliberate
follow-on (§10), not detailed here.

---

## 0. Non-negotiable design principle

**The concierge is measured by guest satisfaction and hotel revenue,
not by how many questions it answers.** Every implementation decision
in this document is subordinate to that. A concierge that confidently
answers 100% of questions but gets 5% of them wrong is worse than one
that answers 80% correctly and escalates the other 20% — the first one
erodes trust with the hotel *and* the guest; the second one builds it.
When in doubt anywhere in this document, escalate rather than answer
imperfectly.

This is also the reason for §1's title distinction: **build a
concierge, not a chatbot.** A chatbot's job is to answer everything. A
concierge's job is four small, specific things (welcome guests, answer
hotel questions, sell hotel services, escalate uncertainty) — and
knowing what it *doesn't* do is what keeps it reliable. Scope discipline
is the feature, not a limitation of one.

## 1. Why this needs a design pass first — and why more than PDF or Email did

PDF and Email Import's worst-case failure is a wrong or skipped
*import* — bad, but caught by a human on a review screen before
anything reaches a guest, and reversible. The AI Concierge's worst-case
failure is a wrong answer **sent directly to a real hotel guest**, with
no review screen in between by design. That's categorically higher
stakes than anything shipped so far, and it's why §6 (escalation rules)
and §4 (the Context Builder) are the load-bearing sections here, the
way §3 was for Email Import's trust model and §4 was for PDF's
confidence gate.

## 2. What already exists (audit, so this doc doesn't redesign it)

| Capability | Status | Where |
|---|---|---|
| WhatsApp outbound send (mock + live) | ✅ Built | `app/integrations/whatsapp.py` |
| Webhook signature verification (HMAC) | ✅ Built | `whatsapp.py: verify_signature` |
| Webhook challenge verification | ✅ Built | `whatsapp.py: verify_webhook_challenge` |
| Inbound text message parsing | ✅ Built (text only) | `whatsapp.py: parse_webhook` |
| Inbound message storage | ✅ Built | `messaging.py: ingest_inbound_whatsapp` |
| Multi-tenant inbound routing | ❌ Not built — **P0, see §3** | hardcodes `tenant_id = "demo-hotel"` |
| Media (image/document/audio) inbound | ❌ Not built | parser only handles `msg.type == "text"` |
| Message templates (Meta's 24h-window rule) | ❌ Not built | no template model/config exists |
| Guest Memory (preferences, complaints, upsell history) | ✅ Largely built | `Guest` model — `preferred_room`, `dietary_preferences`, `birthday`/`anniversary`, `complaint_history`, `upsell_acceptance`, `previous_reviews` |
| Automation trigger engine | ✅ Foundation built | `Workflow`/`WorkflowRun` support arbitrary `trigger` + step sequences |
| "Decide next action" AI (outbound campaigns) | ✅ Built, different shape | `ai_orchestrator.py` — reused by the Revenue Agent (§5.3), not replaced |

## 3. Multi-tenant WhatsApp routing — P0, literally the first implementation task

Confirmed as the correct call: **nothing else in this document matters
until `phone_number_id → tenant` resolution exists.** Meta's inbound
webhook payload already includes `value.metadata.phone_number_id` on
every message; `parse_webhook` currently discards it. Fix: capture that
field, store a `phone_number_id` per tenant (one ReVisit-owned WABA
hosting a distinct number per hotel), and route inbound messages by
looking up which tenant owns the number the message arrived at —
instead of the current hardcoded `"demo-hotel"` or guessing from a
guest phone number. This is a schema change (one new column) plus
reading a field that's already there, not new Meta-side infrastructure.
**Week 1, task 1 — nothing else in §5's agents can be safely built
before this, since without it every reply risks going to, or being
attributed to, the wrong hotel.**

## 4. Architecture: Router → Context Builder → Agents

**The single biggest architecture decision in this document: the LLM
never queries the database.** A `Context Builder` assembles everything
an agent could need into one plain object *before* any model is
called; every agent (§5) only ever reads from that object. This is
what makes hallucination containment tractable — there's no code path
where a prompt can go fetch its own data, so there's no code path where
it can fetch the wrong data or leak another tenant's.

```
WhatsApp inbound
        │
        ▼
Resolve tenant via phone_number_id (§3)
        │
        ▼
             Conversation Router
                    │
                    ▼
             Context Builder
   assembles, once per turn:
   {
     "guest": {...},        // from Guest Memory (§5.2)
     "reservation": {...},  // active/most-recent reservation
     "hotel": {...},        // Property basics
     "knowledge": {...},    // PropertyKnowledgeBase (§6)
     "offers": [...]        // eligible upsell/service offers
   }
                    │
                    ▼
        Human Escalation check FIRST (§7) —
        runs against the raw guest message,
        before any agent or LLM call, full stop
                    │
         ┌──────────┴──────────┐
         │                     │
     matched                not matched
         │                     │
         ▼                     ▼
   Notify staff          Route to exactly one agent:
   (Task/Notification)   FAQ Agent / Guest Memory Agent /
   No AI reply sent.     Revenue Agent (§5) — each receives
                          only the Context Builder's object,
                          never raw DB access
                                    │
                                    ▼
                          Send via WhatsApp, log to
                          conversation history, update
                          Guest Memory if the exchange
                          revealed something worth
                          remembering
```

Router logic for picking an agent is intentionally simple keyword/
intent classification (a hotel-fact question → FAQ Agent; anything
referencing the guest's own history/preferences → Guest Memory Agent;
anything about upgrades/services/pricing → Revenue Agent) — it doesn't
need to be an LLM call itself, and shouldn't be, per §0: fewer AI
decisions in the hot path means fewer places to get something wrong.

## 5. The four agents

Each agent has a small, specific job (§0) and a small, predictable
prompt — this is the point of splitting one loop into four.

### 5.1 FAQ Agent

Answers **only** from `PropertyKnowledgeBase` (§6), delivered via the
Context Builder's `knowledge` field — never invents, never falls back
to general knowledge about hotels in general. If the field the guest is
asking about is empty or absent:

```
I don't know. I'll ask the hotel staff.
```

verbatim in spirit — an honest non-answer, immediately escalated (§7),
never a guess dressed up as an answer.

### 5.2 Guest Memory Agent

**No LLM reasoning required — retrieval only.** Reads the Context
Builder's `guest` field (existing `Guest` model fields, §2) and
produces things like "Welcome back, Mr. Smith — we noticed you enjoyed
the Suite last time." This is template-filling against real data, not
generation; the "AI" here is arguably just formatting, which is exactly
why it's the safest of the four agents and a good one to ship first
after the FAQ Agent.

### 5.3 Revenue Agent

Decides whether to offer an upgrade, spa, breakfast package, airport
pickup, or late checkout, based on stay details, guest history,
occupancy, and timing — this is `ai_orchestrator.py`'s existing "decide
the next best action" logic (§2), adapted to run inside a conversation
turn instead of only on a schedule. Reuses the existing `Offer`/
Approval machinery for anything that becomes a real commercial send —
this agent decides *whether to suggest*, it doesn't independently
invent pricing or bypass the existing offer-approval flow.

### 5.4 Human Escalation

Not an agent that generates anything — a **gate**, checked first, every
turn, before the other three agents are even considered (§4's diagram).
See §7 for the trigger list. "No AI. Ever." on this path means: once
escalated, the concierge sends no further AI-generated reply in that
conversation until a human has responded — it doesn't keep trying to
help around the edges of an escalated topic.

## 6. Knowledge Base — v1 is structured data, not vector retrieval

Confirmed: **no RAG, no vectors, no embeddings.** A `PropertyKnowledgeBase`
entity, one row per property:

| Group | Fields |
|---|---|
| Practical info | wifi_password, checkin_time, checkout_time, parking_info, pool_hours, gym_hours, spa_hours, airport_info |
| House rules & policies | house_rules, policies (free text) |
| Local recommendations | restaurants, cafes, attractions, views — **staff-curated, not AI-generated.** Hotel staff pre-feeds this content as a human reference (their own picks, their own voice); the concierge's job is to *push* it via WhatsApp when asked, not to generate recommendations itself. This matters for the same reason FAQ Agent never invents facts: a hotel recommending a specific restaurant is a human judgment call the hotel should own, not something the AI should guess at even plausibly |
| Services & pricing | services (name + price + how to request), room_service_hours, late_checkout_policy |
| Emergency | emergency_contacts |

Empty field → FAQ Agent's honest non-answer (§5.1) → escalate. Revisit
vector/RAG only if a hotel's local-recommendations content grows large
enough that structured lookup genuinely can't cover it — not before
real usage shows that's needed. At the stated ~90% of guest questions
this structured list should already cover, that bar is far off.

## 7. Escalation rules — expanded, no AI on this path, ever

The concierge escalates immediately, with **zero** AI-generated reply,
when a message matches any of:

- Complaint
- Refund request
- Cancellation request
- Payment dispute
- Emergency
- Injury
- Medical or allergy content of any kind
- Police involvement
- Legal matters
- Abuse
- Threat
- Harassment
- Anything the Knowledge Base doesn't have an answer for (§5.1/§6)
- Anything the guest explicitly asks to speak to a human about

**Detection method matters as much as the list.** Keyword/pattern
matching is fast and fully deterministic but brittle — "I think I might
be allergic" or "my chest hurts" won't match a literal keyword list.
Recommendation: a lightweight, high-recall classification pass (rule-
based patterns *plus* a small, cheap model call whose only job is
"does this need escalation, yes/no + category" — never to answer)
tuned deliberately toward over-escalating rather than under-escalating,
per §0. This classification step is itself a candidate for the same
mock/heuristic-fallback discipline as everywhere else in this app: when
no AI is configured, default to the deterministic keyword pass alone,
which is more conservative (catches less), not less safe (never
answers on a false negative it does catch — it just might miss one a
model would have caught). This tradeoff should be revisited once real
pilot conversations show what's actually being missed.

This list is a floor, not a ceiling — real pilot conversations (§10)
should only ever widen it, never narrow it, absent a specific reason
tied to real observed behavior.

## 8. AI provider, cost, and fallback

Same `AIGateway` contract as PDF/Email (structured-JSON-only,
Pydantic-validated). Split by agent:

- **FAQ Agent**: mostly no LLM call needed at all — matching a guest's
  free-text question to the right `PropertyKnowledgeBase` field is
  closer to intent classification than generation. An LLM call, if
  used, only phrases the answer from the one supplied fact — it never
  has license to add anything not in that fact.
- **Guest Memory Agent**: no LLM reasoning (§5.2) — template-filling.
- **Revenue Agent**: reuses `ai_orchestrator.py`'s existing decision
  contract as-is.
- **Escalation gate**: see §7's detection-method note — a classification
  call, never an answer-generating one.

Mock/no-API-key fallback for any agent that would call an LLM: a fixed
"Thanks for reaching out — a member of our team will get back to you
shortly" plus an automatic escalation, not an attempt at heuristic
conversation (unlike PDF's heuristic extractor, there's no safe regex
substitute for *talking* to a guest).

## 9. Review-flow detection

Reuses the existing review-request machinery unchanged (`Message.
message_type == "review_request"`) — the new part is the Guest Memory
Agent or Revenue Agent triggering it from an explicit positive signal
in conversation, in addition to the existing post-checkout schedule.

## 10. Automation Engine — deliberately not detailed here

`Workflow`/`WorkflowRun` already support arbitrary triggers and step
sequences (§2). Wiring pre-arrival/check-in/mid-stay/checkout/post-
checkout triggers to fire from the event bus is configuration and
event-wiring against an engine that already exists, not new design
risk — it becomes a build task once this doc's conversation loop
exists to be triggered.

## 11. Explicitly out of scope for v1

- **Voice/audio messages** — text only.
- **Vector/RAG knowledge base** — see §6.
- **AI-generated local recommendations** — see §6; this is staff-
  curated content by design, not a v1-vs-later scoping question.
- **Fully autonomous booking modifications** — anything that mutates a
  reservation goes through existing reviewed flows, not directly from
  a chat reply.
- **Per-hotel WhatsApp number self-service provisioning** — v1 assumes
  ReVisit provisions numbers under its own WABA (§3), not a hotel
  self-serve flow.

## 12. Implementation sequence

- **Week 1**: Fix tenant routing (§3). Build the WhatsApp conversation
  service and the Context Builder (§4). No agents yet.
- **Week 2**: Knowledge Base CRUD (§6). FAQ Agent (§5.1). Human
  Escalation gate (§7) — ship escalation *before* any agent that
  generates a reply goes live, not after.
- **Week 3**: Guest Memory Agent (§5.2). Revenue Agent (§5.3).
  Conversation history storage/UI.
- **Week 4**: Pilot with 1–2 hotels. Observe every conversation.
  Improve prompts from what's actually observed, not assumptions.
  Populate `PARSER_BACKLOG.md`-style triage into a new
  `CONCIERGE_BACKLOG.md` from real interactions, same P0–P3 discipline.

## 13. Open questions before implementation starts

1. **Who provisions each tenant's WhatsApp phone number under
   ReVisit's WABA, and how** — a one-time Meta Business step this
   assistant can't perform.
2. **Escalation list in §7 — confirmed and expanded this round; still
   worth a final read before Week 2 ships it**, since it's the one
   place where the conservative failure mode (escalating something
   that could've been auto-answered) is categorically cheaper than the
   permissive one.
3. **Message template strategy for Meta's 24-hour window rule** —
   pre-arrival/post-checkout automation triggers (§10) fire outside any
   active conversation window by definition and need pre-approved
   templates; approval isn't instant.
