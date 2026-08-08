# WhatsApp Conversation Platform + AI Concierge — Design Document

Status: Draft, architecture approved — "crossed from idea into a solid
architecture" per co-founder review. No code has been written against
this document yet; Week 1 (§13) begins once this revision is read.

Scope: this doc covers Phase 1 (WhatsApp Infrastructure, closing the
real gaps) and Phase 2 (AI Concierge), including the Knowledge Base data
model Phase 2 depends on. Guest Memory (Phase 4) is **not** redesigned
here — it's already substantially built (§2) and this doc treats it as
an existing dependency, now formalized as one of the four agents (§5).
Automation Engine trigger wiring (Phase 5) is named as a deliberate
follow-on (§11), not detailed here.

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
stakes than anything shipped so far, and it's why §8 (escalation rules)
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
| Offer catalog (never-invent-pricing convention) | ✅ Already established | `openai_gateway.py`'s system prompt already says "Never invent offers outside the provided catalog" — this is exactly the guardrail the Revenue Agent needs (§5.3), not new policy |

## 3. Multi-tenant WhatsApp routing — P0, literally the first implementation task

Confirmed as the correct call: **nothing else in this document matters
until `phone_number_id → tenant` resolution exists.** Meta's inbound
webhook payload already includes `value.metadata.phone_number_id` on
every message; `parse_webhook` currently discards it.

Implementation: add `Property.whatsapp_phone_number_id` (mirrors how
`Property.address`/`Property.google_review_url` were added earlier —
one property per tenant already, no new table needed), capture
`value["metadata"]["phone_number_id"]` in `parse_webhook`, and route
inbound messages by looking up which tenant's property owns that number
— instead of the current hardcoded `"demo-hotel"` or guessing from a
guest phone number. Schema change plus reading a field that's already
there, not new Meta-side infrastructure. **Task 1 of §13 — nothing else
can be safely built before this, since without it every reply risks
going to, or being attributed to, the wrong hotel.**

## 4. Architecture: Router → Context Builder → Agents → Conversation Manager

**The single biggest architecture decision in this document: the LLM
never queries the database.** A `Context Builder` assembles everything
an agent could need into one **immutable** object *before* any model is
called; every agent (§5) only ever reads from that object. This is what
makes hallucination containment tractable — there's no code path where
a prompt can go fetch its own data, so there's no code path where it
can fetch the wrong data or leak another tenant's.

```
WhatsApp inbound
        │
        ▼
Resolve tenant via phone_number_id (§3)
        │
        ▼
   Escalation Filter (§8) — runs on the raw message,
   before Context Builder, before any agent, full stop.
   Hard safety/urgency categories ONLY (medical, emergency,
   safety, threat, refund/billing, complaint, human-requested)
   — see §4.1 for why "not a KB topic" moved out of here.
        │
   ┌────┴─────┐
   │          │
 Human?      No
  Yes         │
   │          ▼
   ▼      Context Builder — assembles once per turn:
Notify   ┌─────────────────────────────┐
staff    │ Context                     │
(Task/   │ ├── Guest                   │
Notif-   │ ├── Reservation             │
ication) │ ├── Property                │
No AI    │ ├── Knowledge Base          │
reply    │ ├── Services & Packages     │
sent.    │ ├── Conversation History    │
         │ ├── Current Time            │
         │ ├── Previous AI Actions     │
         │ └── Available Automations   │
         └─────────────┬───────────────┘
                        │
                        ▼
              Router (concierge_router.py) — tries each
              agent in fixed priority order, calls exactly
              one, first handled=True wins:
                        │
              ┌─────┬───┴────┬─────────┐
              │     │        │         │
            FAQ  Ordering  Revenue   Guest
           Agent   Agent    Agent   Memory
          (§5.1) (food/    (§5.3)   Agent
                  menu)              (§5.2)
              │     │        │         │
              └─────┴────┬───┴─────────┘
                          ▼
              Router escalates to staff if the agent
              that handled it set should_escalate=True,
              or if NO agent recognized the message at
              all (§0: escalate rather than answer
              imperfectly) — never silently dropped.
                          │
                          ▼
              Conversation Manager (§5.5, not yet built)
                          │
                          ▼
                      WhatsApp
```

### 4.1 Router — deterministic, fixed priority order

Sending every inbound message to an LLM just to decide *which agent*
should handle it is unnecessary latency and cost for the common case.
As built (`concierge_router.py`), the Router is fully deterministic: it
tries each agent in a fixed priority order and returns the first
`handled=True` response, without ever calling more than one agent per
message or letting one agent see another's output:

    FAQ Agent → Ordering Agent (food/menu) → Revenue Agent
    (services & upsells) → Guest Memory Agent → escalate to staff

This keeps responsibilities clean: FAQ answers questions, Ordering
handles food, Revenue sells hotel services and fulfills service
requests, Guest Memory learns from confirmed interactions — and each
agent's own pattern matching (§5.1-§5.3) is precise enough that no LLM
classification pass has been needed to disambiguate between them.
"Restaurant"/"nearby"/"recommend" still routes to FAQ Agent (§5.1's
note on local recommendations — deliberately not a fifth agent).

An LLM fallback classification call, only for messages none of the four
agents recognizes, remains a reasonable future addition — not yet
built; today an unrecognized message escalates to staff instead
(`concierge_router.py`'s own fallback), which is the safer default for
a pre-pilot system with no real conversation volume yet to tune
against.

**FAQ Agent runs first, which creates one subtlety worth being
explicit about**: several Knowledge Base topics (checkout, parking,
spa, gym, airport transfer, breakfast, room service) share a bare
keyword with an actionable Revenue/Ordering Agent request — "what time
is checkout" (FAQ) and "can I check out at 4pm" (Revenue) both mention
"checkout". FAQ Agent defers instead of claiming the topic whenever the
message also matches the corresponding agent's own action-oriented
pattern (`faq_agent.py`'s `_TOPIC_OVERRIDE_SERVICE_TYPES`) — reusing
that agent's already-tested pattern rather than a second heuristic that
could drift out of sync with it.

**On "Local Guide" as its own category**: local recommendations route
to the **FAQ Agent**, not a fifth agent. The FAQ Agent's contract
("answer only from structured/staff-curated data, never invent") is
identical whether the field is `wifi_password` or `restaurants` — the
Knowledge Base already holds both (§7), and §0's scope discipline means
adding agents only when a genuinely different *behavior* is needed, not
one per topic category.

## 5. The four agents (plus one non-agent, the Conversation Manager)

Each agent has a small, specific job (§0) and a small, predictable
prompt — this is the point of splitting one loop into four.

### 5.1 FAQ Agent

Answers **only** from `PropertyKnowledgeBase` (§7), delivered via the
Context Builder's `knowledge` field — never invents, never falls back
to general knowledge about hotels in general. Also handles local-
recommendation queries (§4.1) from the same staff-curated fields. If
the field the guest is asking about is empty or absent:

```
I don't know. I'll ask the hotel staff.
```

verbatim in spirit — an honest non-answer, immediately escalated (§8),
never a guess dressed up as an answer.

### 5.2 Guest Memory Agent — read-only in v1

**No LLM reasoning required for reads — retrieval only.** Reads the
Context Builder's `guest` field (existing `Guest` model fields, §2) and
produces things like "Welcome back, Mr. Smith — we noticed you enjoyed
the Suite last time." Template-filling against real data, not
generation.

**Writes are explicitly gated, not automatic.** If a conversation
reveals something worth remembering (a stated preference, a dietary
note), the agent produces a **suggested edit**, not a database write —
routed through the same "manager approval on every commercial action"
convention already used elsewhere in this app (the existing Approvals
queue), so a hotel staff member confirms it before it's saved to
`Guest`. This prevents profile pollution from a misheard or
misinterpreted remark, and keeps Guest Memory itself trustworthy data
other features (Revenue Agent, the dashboard) already depend on.

### 5.3 Revenue Agent

Decides whether to offer an upgrade, spa, breakfast package, airport
pickup, or late checkout, based on stay details, guest history,
occupancy, and timing — this is `ai_orchestrator.py`'s existing "decide
the next best action" logic (§2), adapted to run inside a conversation
turn instead of only on a schedule.

**Guardrail: never invents a price.** This is already the existing
convention, not new policy — `openai_gateway.py`'s system prompt
already states "Never invent offers outside the provided catalog"
(§2). The Revenue Agent selects from the tenant's existing configured
Offer catalog; it decides *whether and what to suggest*, never *what it
costs*. A live, real-time PMS inventory/pricing sync (an actual
"Upgrade API" pulling current rates from Cloudbeds/Mews/etc.) is future
work tied to those PMS integrations, not a v1 requirement — the catalog
already serves as v1's pricing source of truth, the same way it already
does for every other AI-decided offer in this app today.

### 5.4 Escalation Filter

Not an agent that generates anything — a **gate**, checked first, every
turn, before the Context Builder is even assembled (§4's diagram). See
§8 for the trigger list. "No AI. Ever." on this path means: once
escalated, the concierge sends no further AI-generated reply in that
conversation until a human has responded.

### 5.5 Conversation Manager

The one component that isn't an agent — it sits between an agent's
candidate reply and the actual WhatsApp send, and after only a few
messages this is where a real conversation stops feeling like four
independent one-shot replies and starts feeling coherent. Responsible
for:

- Conversation history (storage + retrieval, feeds the Context
  Builder's `Conversation History` field)
- Summarizing long conversations before they're fed back into context,
  so token cost doesn't grow unbounded with conversation length
- Preventing repeated answers (don't re-explain checkout time if it was
  just given two messages ago)
- Tracking what's already been offered (don't pitch the spa twice in
  one stay if the guest already declined)
- Maintaining a consistent tone across a conversation, independent of
  which of the three reply-generating agents produced the last message
- Throttling AI calls (rate/cost control per conversation, independent
  of the per-tenant rate limiting Email Import's design already
  established for a different reason)

## 6. What "Available Automations" and "Previous AI Actions" mean in the Context Builder

Two of the eight Context Builder fields (§4) aren't obviously covered
elsewhere in this doc, worth being explicit about:

- **Previous AI Actions**: what the concierge (any of the three
  reply-generating agents, across this guest's whole stay, not just
  this conversation) has already said or offered — this is what lets
  the Conversation Manager (§5.5) avoid repeating itself and lets the
  Revenue Agent (§5.3) avoid re-pitching a declined offer.
- **Available Automations**: which `Workflow` triggers (§2, §11) are
  live for this property right now — e.g. so the concierge doesn't
  promise a pre-arrival message the hotel hasn't actually configured.

Both are read from existing data (`Message`/`Offer` history, `Workflow`
config) — no new tracking system, just two more fields the Context
Builder assembles.

## 7. Knowledge Base — v1 is structured data, not vector retrieval

Confirmed: **no RAG, no vectors, no embeddings.** A `PropertyKnowledgeBase`
entity, one row per property:

| Group | Fields |
|---|---|
| Practical info | wifi_password, breakfast_hours, pool_hours, gym_hours, spa_hours, parking_info, checkin_time, checkout_time, late_checkout_policy, airport_transfer_info |
| Policies | pet_policy, house_rules, policies (free text) |
| Local recommendations | restaurants, cafes, nearby_attractions — **staff-curated, not AI-generated.** Hotel staff pre-feeds this content as a human reference (their own picks, their own voice); the concierge's job is to *push* it via WhatsApp when asked (§4.1, §5.1), not to generate recommendations itself. A hotel recommending a specific restaurant is a human judgment call the hotel should own |
| Services & pricing | services (name + price + how to request), room_service_hours |
| Emergency | emergency_contacts |

Empty field → FAQ Agent's honest non-answer (§5.1) → escalate. Revisit
vector/RAG only if a hotel's local-recommendations content grows large
enough that structured lookup genuinely can't cover it — not before
real usage shows that's needed. At the stated ~90% of guest questions
this structured list should already cover, that bar is far off.

## 8. Escalation rules — expanded, no AI on this path, ever

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
- Anything the Knowledge Base doesn't have an answer for (§5.1/§7)
- Anything the guest explicitly asks to speak to a human about

**Detection method matters as much as the list.** Keyword/pattern
matching is fast and fully deterministic but brittle — "I think I might
be allergic" or "my chest hurts" won't match a literal keyword list.
Recommendation: a lightweight, high-recall classification pass (rule-
based patterns *plus* a small, cheap model call whose only job is
"does this need escalation, yes/no + category" — never to answer)
tuned deliberately toward over-escalating rather than under-escalating,
per §0. When no AI is configured, default to the deterministic keyword
pass alone — more conservative (catches less), not less safe (never
answers on a false negative it does catch). This tradeoff should be
revisited once real pilot conversations show what's actually missed.

This list is a floor, not a ceiling — real pilot conversations (§13
step 9) should only ever widen it, never narrow it, absent a specific
reason tied to real observed behavior.

## 9. AI provider, cost, and fallback

Same `AIGateway` contract as PDF/Email (structured-JSON-only,
Pydantic-validated). Split by agent:

- **FAQ Agent**: mostly no LLM call needed at all — matching a guest's
  free-text question to the right `PropertyKnowledgeBase` field is
  closer to intent classification than generation. An LLM call, if
  used, only phrases the answer from the one supplied fact.
- **Guest Memory Agent**: no LLM reasoning for reads (§5.2); writes are
  approval-gated, not autonomous.
- **Revenue Agent**: reuses `ai_orchestrator.py`'s existing decision
  contract and catalog constraint as-is (§5.3).
- **Escalation Filter**: see §8's detection-method note — a
  classification call, never an answer-generating one.
- **Router** (§4.1): deterministic first; LLM fallback is also
  classification-only.

Mock/no-API-key fallback for any agent that would call an LLM: a fixed
"Thanks for reaching out — a member of our team will get back to you
shortly" plus an automatic escalation, not an attempt at heuristic
conversation (unlike PDF's heuristic extractor, there's no safe regex
substitute for *talking* to a guest).

## 10. Review-flow detection

Reuses the existing review-request machinery unchanged (`Message.
message_type == "review_request"`) — the new part is the Guest Memory
Agent or Revenue Agent triggering it from an explicit positive signal
in conversation, in addition to the existing post-checkout schedule.

## 11. Automation Engine — deliberately not detailed here

`Workflow`/`WorkflowRun` already support arbitrary triggers and step
sequences (§2). Wiring pre-arrival/check-in/mid-stay/checkout/post-
checkout triggers to fire from the event bus is configuration and
event-wiring against an engine that already exists, not new design
risk — it becomes a build task once this doc's conversation loop
exists to be triggered. This is what "Available Automations" (§6)
reads from once it exists.

## 12. Explicitly out of scope for v1

- **Voice/audio messages** — text only.
- **Vector/RAG knowledge base** — see §7.
- **AI-generated local recommendations** — see §7; staff-curated by
  design, not a v1-vs-later scoping question.
- **Fully autonomous booking modifications** — anything that mutates a
  reservation goes through existing reviewed flows, not directly from
  a chat reply.
- **Autonomous Guest Memory writes** — see §5.2; suggestion + staff
  approval only.
- **Live PMS inventory/pricing sync for the Revenue Agent** — see
  §5.3; the existing Offer catalog is v1's pricing source.
- **Per-hotel WhatsApp number self-service provisioning** — v1 assumes
  ReVisit provisions numbers under its own WABA (§3), not a hotel
  self-serve flow.

## 13. Implementation sequence

1. Multi-tenant WhatsApp routing (§3)
2. Context Builder (§4)
3. Conversation Manager (§5.5)
4. Escalation Filter (§5.4, §8)
5. FAQ Agent (§5.1)
6. End-to-end WhatsApp conversation (steps 1–5 wired together, no
   Guest Memory or Revenue Agent yet — this is the first point a real
   message can flow through the whole pipeline)
7. Guest Memory Agent (§5.2)
8. Revenue Agent (§5.3)
9. Pilot with 1–2 hotels. Observe every conversation. Improve prompts
   from what's actually observed, not assumptions. Populate
   `CONCIERGE_BACKLOG.md` from real interactions, same P0–P3 discipline
   as `PARSER_BACKLOG.md`.

Escalation (step 4) intentionally ships before any reply-generating
agent (step 5+) — per §0, nothing answers a guest until the gate that
decides *whether* to answer exists.

## 14. Open questions before implementation starts

1. **Who provisions each tenant's WhatsApp phone number under
   ReVisit's WABA, and how** — a one-time Meta Business step this
   assistant can't perform. Doesn't block step 1–6 in mock mode, but
   blocks any real pilot conversation (step 9).
2. **Message template strategy for Meta's 24-hour window rule** —
   pre-arrival/post-checkout automation triggers (§11) fire outside any
   active conversation window by definition and need pre-approved
   templates; approval isn't instant.

(Escalation list, §8, and the Router's deterministic-first design, §4.1,
are resolved as of this revision — not carried forward as open
questions.)
