# AI Concierge — Menu Management, Meal Reservation & Room Service Ordering

Status: **Roadmap document, deliberately not an implementation
commitment.** The three open questions below are resolved, but
implementation is explicitly deferred until the AI Concierge core
(Concierge Router + first pilot) is complete — this doc documents a
future subsystem without expanding the current pilot's surface area.
Revisit once real pilot conversations show ordering is worth building
next, per CONCIERGE.md §0's own principle applied to itself.

---

## 1. Why this needs a design pass first — and why more than the agents shipped so far

Every agent shipped so far (FAQ, Guest Memory) either answers from
static Knowledge Base text or proposes a data change for something else
to apply — neither one moves money or creates an obligation the hotel
has to fulfill. Room service ordering does both: a confirmed order is a
promise to a guest and, at some hotels, a charge. A wrong price, a
phantom order, or an order the kitchen never receives is a materially
worse failure than a wrong FAQ answer — it's the first Concierge
capability where a mistake costs the hotel real money or a guest's
trust in a single, concrete transaction, not just an unhelpful reply.

This is also the first Concierge capability that is inherently
**multi-turn** (propose a cart → guest confirms → order is placed),
which every agent built so far deliberately was not. That has one real
architectural consequence covered in §7.

## 2. Scope for v1

| In scope | Out of scope (future, per spec) |
|---|---|
| PDF and Excel/CSV menu upload | Image upload with AI extraction |
| Structured menu items (name, category, price, availability, dietary tags) | POS integration |
| Meal reservation (pre-arrival) | — |
| Room service ordering (in-stay) | — |
| Order history (event log) | — |
| Memory proposals from confirmed order patterns | — |
| Personalized recommendations from menu + order history + approved memories | — |

## 3. Menu Manager

### 3.1 Data model

A new `MenuItem` entity, one row per dish/drink, scoped to a property
(a hotel can have several menus — breakfast, lunch, dinner, room
service, bar, spa refreshments — distinguished by `menu_name`, not by
separate tables):

| Field | Notes |
|---|---|
| `tenant_id`, `property_id` | same scoping as every other entity |
| `menu_name` | "Breakfast Menu", "Room Service Menu", etc. |
| `name` | dish/drink name |
| `category` | "Main Course", "Starter", "Dessert", "Beverage", etc. |
| `description` | optional |
| `price`, `currency` | |
| `available` | boolean — a hotel can 86 an item without deleting it |
| `vegetarian`, `vegan`, `gluten_free` | booleans, matching the spec's example exactly |
| `spicy` | boolean |
| `source_import_id` | which upload created this row (reuses the `ImportSession` pattern already established for every other bulk-ingest source in this app — a menu upload **is** an import, just into a new table) |

### 3.2 Upload pipeline — reuses existing infrastructure, doesn't reinvent it

```
Hotel uploads Menu (PDF or Excel/CSV)
        │
        ├── PDF ──────────► app/integrations/pdf_extractor.py
        │                   (existing, unmodified — PDF_IMPORT.md §3)
        │                            │
        │                            ▼
        │                   AI Parser — new extraction schema
        │                   (menu items, not reservations), same
        │                   AIGateway contract, same heuristic
        │                   fallback discipline as pdf_ai_parser.py
        │
        └── Excel/CSV ────► new spreadsheet reader (openpyxl for
                             .xlsx — new dependency, same tier as
                             pdfplumber; CSV reuses the stdlib `csv`
                             reader routes.py's _read_csv_rows already
                             uses)
                                     │
                                     ▼
                          Structured rows, same shape either path
                                     │
                                     ▼
                        Review screen (PDF_IMPORT.md §7's exact
                        pattern: Ready to Import / Needs Review per
                        row, human approves before anything writes —
                        a menu item with a garbled price is worse than
                        a garbled reservation, since it's live the
                        moment a guest orders it)
                                     │
                                     ▼
                          MenuItem rows created, ImportSession
                          created with source="menu"
```

**This is the same Importer Protocol shape PDF Import already
formalized** (`app/services/importer.py`) — a `MenuImporter` is a
natural second/third implementer, following the exact precedent
`PdfImporter` set. A PDF menu literally reuses `pdf_extractor.py`
unmodified; only the AI Parser's extraction schema (menu items instead
of reservations) and the target table differ.

### 3.3 Editing

Hotels can edit price, availability, description, category, and
dietary tags after upload — a straightforward CRUD endpoint on
`MenuItem`, same shape as `PropertyUpdate`'s pattern (`PATCH` by ID,
tenant-scoped). This is also where `PropertyKnowledgeBase`'s own
still-missing editor (task #44's open half) and the menu editor should
probably share a UI section, since both are "hotel staff manage the
facts the concierge is allowed to state" — worth building together
rather than as two unrelated screens.

**Cache invalidation applies here too**: any menu edit (or import) must
call `ContextBuilder.invalidate_tenant(tenant_id)` (the primitive added
in PR #14's review) for the same reason a Knowledge Base edit does — a
stale cached menu is a guest ordering a dish that was 86'd five minutes
ago.

## 4. Extending the Context Builder

`ConciergeContext` (§4 of CONCIERGE.md) gains two new fields, assembled
the same way everything else on it is — read-only, tenant-scoped, no
agent queries the database directly:

```
ConciergeContext
├── ...(unchanged)...
├── Menu Items          — this property's available items, grouped by
│                          menu_name, only where available=True
├── Order History        — this guest's confirmed orders, most recent
│                          first (mirrors Conversation History's shape)
└── Pending Order         — see §7; the one stateful piece
```

## 5. Meal Reservation (pre-arrival)

A conversation the concierge can *initiate* (not just respond to) a few
days before arrival — this is the first Concierge capability that
sends the first message, which is itself worth calling out: every
agent shipped so far only ever replies. Initiating this conversation is
an **Automation Engine** trigger (CONCIERGE.md §11, `Workflow`/
`WorkflowRun` — already built, just not yet wired to fire this
specific message), not new agent logic.

Once the guest engages, the flow is conversational and menu-scoped
exactly as specified: meal type → the concierge shows only items from
that menu → guest selects → a `MealReservation` (or simply an `Order`
with `order_type="meal_reservation"` and a future `scheduled_for`
timestamp — see §6, one entity likely covers both cases) is created,
linked to the guest's `Reservation`.

## 6. Room Service Ordering (in-stay)

Same menu-driven, guest-initiated flow. One new entity:

```
Order
├── tenant_id, guest_id, reservation_id
├── order_type            "meal_reservation" | "room_service"
├── status                 pending_confirmation | confirmed | received |
│                           preparing | delivered | cancelled
│                           (resolved, §16.3 — the four fulfillment
│                           states after "confirmed" are exactly the
│                           ones hotel staff set by hand; no POS in v1)
├── scheduled_for           nullable — set for meal reservations, null for
│                           an immediate room-service order
├── items                   [{menu_item_id, name, price, quantity}]
│                           (JSON, same convention as Workflow.definition —
│                           snapshot of name/price at order time, since a
│                           later menu price change shouldn't retroactively
│                           change what a guest already ordered)
├── total_amount, currency
└── created_at, confirmed_at
```

Filtering ("show vegetarian options") is a property lookup against the
already-assembled `context.menu_items` — no new logic beyond what
`FAQAgent`'s Knowledge Base matching already demonstrates: filter,
don't infer.

## 7. The one genuinely new architectural piece: multi-turn confirmation

Every agent shipped so far (`FAQAgent`, `GuestMemoryAgent`) is a pure,
single-turn function: one message in, one `AgentResponse` out, no
memory of the previous turn. Ordering cannot work that way — "Confirm
Order?" followed by "yes" requires the second turn to know what the
first turn proposed.

This is exactly what the **Conversation Manager** (CONCIERGE.md §5.5)
was scoped to own, and it was never actually built — the shipped
sequence went Context Builder → Escalation Filter → FAQ Agent → Guest
Memory Agent, skipping it. Ordering is the first capability that
structurally requires it, not an optional nice-to-have anymore.

Proposed mechanism, kept as narrow as the rest of this app's
"deterministic first" discipline:

- A proposed-but-unconfirmed cart is persisted as a real `Order` row
  with `status="pending_confirmation"` — not agent-internal state
  (agents still don't hold memory across calls), but a real, queryable
  fact the Context Builder can read back next turn (`Pending Order` in
  §4).
- The **Ordering Agent** (new `Agent` Protocol implementer, introduced in this section) checks
  `context.pending_order` first: if one exists and the guest's message
  matches a confirmation phrase ("yes", "confirm", "place the order"),
  it returns `AgentResponse(handled=True, metadata={"action":
  "confirm_order", "order_id": ...})` — a proposed action, not a write
  the agent performs itself, same "propose, don't execute" pattern
  `GuestMemoryAgent`'s `memory_updates` already established. Whatever
  wires the agent in (not yet built — the Concierge Router, roadmap
  step 7) is what actually flips the `Order` row to `confirmed`.
- If no pending order and the message is a new ordering request, the
  agent creates the `pending_confirmation` row itself (this is the one
  place an agent's `answer()` needs to write — a deliberate, narrow
  exception, scoped to exactly one row, one status value, reversible by
  simply never confirming it) and returns the cart summary as `response`
  for confirmation.

This keeps confirmation state in the database (inspectable, survives a
process restart, tenant-isolated by construction) rather than inventing
an in-memory session concept, and keeps every other agent's "never
writes" rule intact by treating this as the Conversation Manager's
job, finally built for the reason it was originally scoped for.

## 8. Order History

A confirmed `Order` **is** the history — no separate event log table
needed; `db.query(Order).filter(guest_id=...).order_by(created_at.desc())`
already gives exactly the "Order History" shown in §4 of the product
spec, the same way `Reservation` rows already serve as a guest's stay
history without a parallel log table.

## 9. Guest Memory: two tracks, not a replacement

Reconciling this spec with what `GuestMemoryAgent` (PR #15, merged)
already does:

| Track | Trigger | Confidence | Status |
|---|---|---|---|
| Explicit self-statement | "I'm vegetarian," "I have a gluten allergy," "I prefer a quiet room," "I always book king beds" | High, immediate | **Already built** (PR #15) — kept as-is; an explicit statement is not "casual conversation," it's a guest directly telling you a fact |
| Accumulated order-pattern evidence | 5 vegetarian orders across stays, zero non-vegetarian | Builds over multiple confirmed `Order` rows | **New**, this doc |

Both tracks produce the *same* `memory_updates` shape
(`{field, value, confidence}`) — the pattern-evidence track just
computes `confidence` from a real distribution (e.g. `vegetarian_orders
/ total_food_orders` over a minimum sample size, not "3 orders and
we're sure") instead of a fixed per-pattern constant.

**Minimum evidence threshold (resolved, §16.1)**: frequency *and*
recency both required, not either alone —

- at least 3 confirmed orders supporting the pattern,
- across 2 or more separate stays (not 3 orders in one long weekend),
- within the last 24 months (a preference from 3 years ago may no
  longer hold).

This avoids learning from a one-off vacation choice while still
adapting if a guest's preferences genuinely change over time —
"ordered a salad twice" isn't "vegetarian," and guessing that too
eagerly is exactly the "never invent guest traits" guardrail this whole
document restates in §12.

## 10. Memory Manager — the "apply" step, finally named

CONCIERGE.md §5.2 always said applying a `memory_updates` proposal was
"a separate concern, not yet built." This spec names it: the **Memory
Manager**. Its job, and only its job:

```
Memory Proposals (from either Guest Memory track, §9)
        │
        ▼
   Memory Manager
        │
   ┌────┼────┬─────────┐
   ▼    ▼    ▼         ▼
Create Merge Ignore  Overwrite
        │
        ▼
   Guest Profile (the real Guest row)
```

This is the only place in the entire Concierge stack that writes
guest-facing memory data — every agent proposes, nothing else writes.
Decision rules (starting point, tune from pilot data per CONCIERGE.md
§0):

- **Create**: no existing value for that field, confidence above
  threshold.
- **Merge**: existing value is compatible (e.g. adding "Allergic to
  peanuts" alongside an existing "Vegetarian" — different facts, not a
  conflict).
- **Ignore**: confidence below threshold, or the proposal duplicates
  what's already stored.
- **Overwrite**: existing value present, new proposal contradicts it,
  and confidence clears a *higher* bar than a fresh create would (same
  "never overwrite without high confidence" rule CONCIERGE.md's Guest
  Memory Agent review already established — the Memory Manager is
  where that rule actually gets enforced, since the agent itself never
  applies anything).

## 11. Personalized recommendations

Explicitly grounded in three sources only, matching the "no
hallucinated recommendations" guardrail: uploaded menu items, confirmed
`Order` history, and Memory Manager-approved (not merely proposed)
memories. A Revenue Agent (roadmap step 6, not yet built) is the
natural home for turning "last time you enjoyed Italian" into an actual
message — this section doesn't add a new agent, it's a note that
Revenue Agent's eventual context should include menu + order history
once §4's Context Builder extension ships.

## 12. AI Guardrails (restated as this doc's contract, not just a list)

- Never invent menu items or recommend food not in the uploaded menu —
  enforced structurally: the Ordering Agent only ever reads from
  `context.menu_items`, never generates a dish name.
- Never assume dietary preferences from casual conversation — enforced
  by keeping the two Guest Memory tracks (§9) as the only paths to a
  proposal; there is no third "infer from tone" path.
- Never save memories from a single casual message — the pattern-
  evidence track (§9) requires multiple confirmed orders; the explicit-
  statement track (already built) is not "casual," it's a direct
  statement, and stays immediate per the resolved decision at the top
  of this doc's history.
- Ask for confirmation before placing any order — enforced by §7's
  `pending_confirmation` status; nothing reaches `confirmed` without an
  explicit guest message matching a confirmation phrase.
- Use only the hotel's uploaded menu and Knowledge Base — same
  structural enforcement as the first bullet.

## 13. Architecture (restated with existing-component references)

```
Hotel uploads Menu
        │
        ▼
  Menu Manager (§3) — reuses pdf_extractor.py / AIGateway,
  same Importer Protocol shape as PdfImporter
        │
        ▼
  MenuItem table
        │
        ▼
  Context Builder (extended, §4) ── ConciergeContext.menu_items
        │
        ▼
  Ordering Agent (new Agent Protocol implementer, §6/§7)
        │
 ┌──────┴──────┐
 ▼             ▼
Meal          Room Service
Reservation   Ordering
 │             │
 └──────┬──────┘
        ▼
     Order (status-driven, §6/§7)
        │
        ▼
  Order History (§8 — just a query, no new table)
        │
        ▼
  Guest Memory Agent, pattern-evidence track (§9, new)
        │
        ▼
  Memory Manager (§10, new — the only writer)
        │
        ▼
  Guest Profile
```

## 14. Explicitly out of scope for v1

- Image menu upload with AI extraction (per spec — future).
- POS integration (per spec — future).
- Multi-currency menus within one property (menu items inherit the
  property's currency, same as everything else in this app).
- Order modification after confirmation (cancel/re-order is a new
  Order, not an edit to a confirmed one — keeps the "snapshot at order
  time" invariant in §6 simple).

## 15. Roadmap positioning

This document is intentionally frozen at the design stage. The AI
Concierge roadmap (CONCIERGE.md) stays on its own track — Revenue Agent
→ Concierge Router → end-to-end WhatsApp conversation tests → first
pilot — without this document adding to that surface area. Per
CONCIERGE.md §0 applied to the roadmap itself: real pilot conversations
should decide whether ordering is the next thing worth building, not
this document's own existence. Revisit only after the pilot is running.

## 16. Decisions (resolved)

1. **Minimum evidence threshold for the order-pattern Guest Memory
   track** (§9): frequency *and* recency both required — at least 3
   confirmed orders supporting the pattern, across 2 or more separate
   stays, within the last 24 months. See §9 for the full reasoning.
2. **Excel parsing dependency**: `openpyxl` for `.xlsx` — mature,
   widely used, pure-Python, fits the existing stack (same tier as
   `pdfplumber`). Legacy `.xls` support waits until a real pilot hotel
   actually needs it, not built speculatively.
3. **How hotel staff receive orders**: no POS integration in v1.
   Guest confirms → an internal `Order` is created → hotel staff are
   notified through ReVisit (reusing the Escalation Filter's `Task`
   staff-queue pattern, CONCIERGE.md §5.4/§8, rather than a parallel
   notification surface) → staff manually advance status through
   `received` → `preparing` → `delivered` (or `cancelled`), per §6's
   updated `Order.status` enum. POS integration is a fast-follow once
   pilots validate the manual workflow is worth automating.

## 17. Implementation sequence (for when this is picked back up)

Proposed, in order: (1) `MenuItem`
   model + migration, (2) menu upload pipeline (PDF path first, reusing
   existing infra directly; Excel/CSV path second), (3) menu editor
   endpoint, (4) Context Builder extension (`menu_items`,
   `order_history`, `pending_order`), (5) `Order` model + migration,
   (6) Ordering Agent (room service first — simpler, single-turn-per-
   item-selection; meal reservation second, since it additionally needs
   the Automation Engine trigger from §5), (7) Memory Manager, (8)
   order-pattern Guest Memory track. Each as its own reviewed PR, same
   discipline as every Concierge PR so far.
