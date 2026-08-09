# AI Concierge — Menu Management, Meal Reservation & Room Service Ordering

Status: **§3 (Menu Manager) and §6/§7 (Ordering Agent) are both fully
implemented (§17 steps 1–10).** `MenuItem` model + migration, the
PDF-only upload/review/confirm pipeline (`menu_ai_parser.py`,
`menu_parser.py`, `menu_importer.py`), and the menu editor endpoint
shipped first; the Ordering Agent build-out followed in four sequenced
PRs against the frozen §6/§7 design: the `PendingAction.payload`/
`origin_agent` schema extension + `ClarifiableAgent` protocol +
`Order`/`OrderItem` models, Conversation Manager's generic dispatch-back
mechanism, the `menu_items`/`order_history` `ConciergeContext`
extension, and finally `ordering_agent.py` itself (deterministic
item/quantity/variant matching against `context.menu_items`, the
`on_order_confirmed` snapshot handler, and Router wiring). Meal
reservation (§5), the order-pattern Guest Memory track (§9), and
personalized recommendations (§11) remain deliberately deferred, per
this document's own explicit out-of-scope list (§14) and the roadmap's
"pilot before more agents" discipline (§15).

**Frozen v1 sub-scope decisions for the Menu Importer** (locked before
implementation, superseding a few specifics below where they differ):
PDF only, no Excel/CSV yet (Excel/CSV in §2's table stays a real future
option, not built speculatively); no separate menu-version table — a
`MenuItem`'s provenance is `source_import_id` (which upload produced
it) plus the existing `AuditLog` (was it subsequently edited by staff),
not a new subsystem; `MenuItem.id` stays stable and immutable across
edits (update in place, never delete-and-recreate) specifically because
a future `Order.items` snapshot (§6) is the actual evidence boundary
that answers "which menu version produced this order," not a table on
`MenuItem` itself; a re-upload of a revised menu creates fresh rows
rather than attempting to fuzzy-match against existing ones (§3.2's own
note, added during implementation). `ConciergeContext` was later
extended with `menu_items`/`order_history` (§4) once the Ordering Agent
became a real consumer — not preemptively, per this same discipline.

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

**Re-uploading a revised menu creates fresh `MenuItem` rows, not a
merge** — decided during implementation, not originally specified here.
Fuzzy-matching a re-extracted item against an existing one (by name, the
only stable-ish signal available) is exactly the kind of guess this
codebase avoids elsewhere; a hotel re-uploading a changed menu ends up
with both the old and new rows, and marks the old ones unavailable or
edits them directly via §3.3's editor. A "supersede this upload's
items" convenience is a reasonable future addition once a pilot hotel
actually needs it, not built speculatively.

### 3.3 Editing — implemented

Hotels can edit price, availability, description, category, and
dietary tags after upload: `PATCH /api/menu-items/{id}` (tenant-scoped,
manager-only), same shape as the now-shipped Knowledge Base Editor's
own `PATCH` endpoint — partial updates only, audited via `AuditLog`
with changed field names, never values. A shared frontend UI section
for both editors (this paragraph's original suggestion) is deferred —
the Menu Importer shipped its editor as an API-only surface for now, a
review/upload UI and a combined "hotel staff manage the facts" screen
are natural, separate follow-ups.

**Cache invalidation does NOT apply yet.** `PR #14`'s
`ContextBuilder.invalidate_tenant(tenant_id)` matters once something
actually reads menu data out of a cached `ConciergeContext` — that's
§4's Context Builder extension, not yet built (see this document's
status line). Calling it today would be a no-op wired to a cache that
holds nothing menu-related; it belongs in the same PR that adds
`menu_items` to `ConciergeContext`, not this one.

## 4. Extending the Context Builder

`ConciergeContext` gains two new **read-only** fields, assembled the
same way everything else on it is — no agent queries the database
directly:

```
ConciergeContext
├── ...(unchanged)...
├── Menu Items          — this property's available items, grouped by
│                          menu_name, only where available=True
└── Order History        — this guest's confirmed Order rows, most
                            recent first (mirrors Conversation History's
                            shape)
```

**No "Pending Order" field here** — that was this document's
pre-Conversation-Manager draft (a raw `Order` row with
`status="pending_confirmation"`, read back from `ConciergeContext`).
Now that Conversation Manager and `PendingAction` actually exist
(CONCIERGE.md §16, built after this document's original draft), the
in-progress cart lives in `PendingAction.payload` instead — and the
Router's own gate (`find_active()` before Intent Classification)
already hands a message straight to Conversation Manager whenever one
exists, so Ordering Agent never needs to read it back off
`ConciergeContext` itself. See §7.

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

## 6. `Order` / `OrderItem` — the durable, confirmed business object

**An `Order` is created at confirmation, never at proposal.** While a
cart is being assembled or clarified, it exists only as
`PendingAction.payload` (§7) — transient, disposable if the guest never
confirms. This is deliberate, not an implementation detail: an
abandoned cart must never look like a business transaction in the data
Argus eventually learns from. "Guest intended to order" and "guest
actually ordered" have to stay distinguishable, and the only way to
guarantee that is to never write an `Order` row for the first case.

```
Order
├── tenant_id, property_id, guest_id, reservation_id
├── correlation_id        — shared with the ORDER_PROPOSED event that
│                           preceded it, minted when the cart itself
│                           was first started (see §7) — the same id
│                           threads guest intent -> proposal ->
│                           confirmation -> Order -> staff execution
├── source_menu_import_id — nullable, provenance mirroring MenuItem's
│                           own (which upload the ordered items came
│                           from, for the same reason MenuItem tracks it)
├── status                 confirmed | received | preparing | delivered
│                           | cancelled (resolved, §16.3 — no
│                           "pending_confirmation" state on Order
│                           itself; that phase is PendingAction's job,
│                           not Order's — an Order only ever starts
│                           existing already-confirmed)
├── total_amount, currency
├── created_at, confirmed_at
```

```
OrderItem
├── order_id
├── menu_item_id  — reference, kept even though the fields below are
│                   snapshotted, so "show me every order of this dish"
│                   stays queryable
├── name, price, currency  — snapshotted at confirmation time; a later
│                             menu price edit never retroactively
│                             changes what a guest already agreed to
│                             (MenuItem's own stable-id guarantee is
│                             what makes this snapshot meaningful —
│                             see MENU_ORDERING.md's Menu Importer
│                             section)
├── quantity
```

Filtering ("show vegetarian options") is a property lookup against the
already-assembled `context.menu_items` — no new logic beyond what
`FAQAgent`'s Knowledge Base matching already demonstrates: filter,
don't infer.

## 7. The multi-turn mechanism: cart-building, clarification, and confirmation

Every agent shipped so far (`FAQAgent`, `GuestMemoryAgent`, Ordering
Agent v0) is a pure, single-turn function — one message in, one
`AgentResponse` out, no memory of the previous turn. A cart genuinely
isn't: "I'd like a burger" (missing quantity) → "two" → "anything
else?" → "no, that's it" → "confirm?" → "yes" is several turns, each
depending on what the previous one established.

Conversation Manager and `PendingAction` (CONCIERGE.md §16) already
solve the *final* step of this — a complete proposal awaiting a plain
yes/no — for Revenue Agent's offers. Ordering needs the same mechanism
extended one step earlier, to cover the *cart-building* turns before a
proposal is even complete enough to ask a yes/no question about.

### 7.1 `PendingAction` schema extension (locked)

Two new columns, generalized — not order-specific — since any future
multi-turn workflow can reuse them:

- **`payload: Text, nullable`** — a JSON blob whose *shape* is entirely
  owned by whichever agent created it; Conversation Manager itself
  only ever inspects one shared, minimal convention: a top-level
  `"complete": bool`. Everything else inside is opaque to Conversation
  Manager. For Ordering, `payload` holds
  `{"complete": bool, "cart": [{"menu_item_id", "name", "price",
  "currency", "quantity"}], "unresolved": {...}}` — the unresolved
  slot's shape is Ordering Agent's own business.
- **`origin_agent: String, nullable`** — which agent to hand a non-final
  reply back to (`"ordering"` today; `None` for the existing
  confirm/cancel-only flows, which never need this).

**`origin_action_type` becomes nullable.** Today it's always a real,
already-logged `action_type` (`"OFFER_PROPOSED"`, etc.) because a
`PendingAction` was never created before something was actually
proposed. A cart under construction hasn't been proposed yet — no
`ActionEvent` exists for it at all (§7.3) — so `origin_action_type` is
`None` for as long as `payload.complete == False`, and only gets set
to `"ORDER_PROPOSED"` the moment the cart is actually complete and an
`ActionEvent` is finally logged for it.

### 7.2 The `ClarifiableAgent` protocol and Conversation Manager's dispatch

A small addition to `agent_protocol.py`, alongside the existing `Agent`
protocol:

```python
class ClarifiableAgent(Protocol):
    def clarify(
        self, context: ConciergeContext, message_body: str, payload: dict
    ) -> AgentResponse: ...
```

Only Ordering Agent implements this today. `Conversation Manager`
keeps a small registry (`{"ordering": ordering_agent}`, mirroring
`_CONFIRMABLE_ACTION_TYPES`'s own "small lookup dict" convention) and
`resolve()` gains a branch **before** its existing confirm/cancel
pattern matching:

```
resolve(pending, message_body):
    if pending.origin_agent and not pending.payload["complete"]:
        # Cart still being built -- hand the reply back to whichever
        # agent started it, not to confirm/cancel matching.
        response = registry[pending.origin_agent].clarify(
            context, message_body, json.loads(pending.payload)
        )
        new_payload = response.metadata["payload"]
        if new_payload["complete"]:
            # First time this cart is a real proposal: mint the
            # ActionEvent now, not before.
            event = log(ORDER_PROPOSED, actor=AI, correlation_id=pending.correlation_id)
            pending.origin_action_type = "ORDER_PROPOSED"
        pending.payload = json.dumps(new_payload)
        return response
    # else: existing confirm/cancel pattern matching, unchanged.
```

`AgentResponse.metadata["payload"]` is how `clarify()` (and the first
call to `answer()` that starts a cart) hands its updated cart state
back — the same "propose via metadata" convention `GuestMemoryAgent`'s
`memory_updates` already established, just carrying a richer shape.

### 7.3 No `ActionEvent` while a cart is incomplete

**A cart under construction generates no ledger entries at all** —
consistent with §6's "an `Order` only exists once confirmed": if the
proposal itself doesn't exist yet, there's nothing honest to log.
`ORDER_PROPOSED` is logged exactly once, the turn the cart first
becomes complete (whether that's turn 1, because the guest stated
everything at once, or turn *N*, after several rounds of
clarification) — never per clarification turn. This also means
`expire_stale()` (Conversation Manager, unchanged mechanism) behaves
differently for the two cases: a `PendingAction` that expires while
still incomplete (`payload.complete == False`) is simply closed, no
new `ActionEvent` — nothing was ever proposed, so nothing "expired" in
the Action Ledger's own sense. Only a *complete*, formally proposed
cart that times out unconfirmed logs `ORDER_EXPIRED` (§7.4) — the same
distinction that already exists between "abandoned cart" and
"unanswered offer."

### 7.4 Confirmation boundary — extends `_CONFIRMABLE_ACTION_TYPES`

```python
"ORDER_PROPOSED": ("ORDER_CONFIRMED", "ORDER_REJECTED", "ORDER_EXPIRED")
```

- **`ORDER_CONFIRMED`** (`actor=GUEST`) — the guest said yes. This is
  the one moment the `Order`/`OrderItem` rows are actually created,
  snapshotting `payload.cart` (§6). Followed immediately by
  **`TASK_CREATED`** (`actor=SYSTEM`) — no PMS/kitchen integration
  exists, so a staff `Task` is the only execution path, exactly the
  pattern `OFFER_ACCEPTED → TASK_CREATED` already established.
- **`ORDER_REJECTED`** (`actor=GUEST`) — the guest declined a *complete*
  proposal before ever confirming it. Deliberately not
  `ORDER_CANCELLED` (already reserved in CONCIERGE.md's frozen
  `action_type` table) — that value means something different and
  later: a *confirmed* order the guest or staff subsequently cancels.
  Collapsing "never confirmed" and "confirmed then cancelled" into one
  value would blur exactly the signal Argus needs, the same reasoning
  that kept `MEMORY_HELD` distinct from `MEMORY_REJECTED`.
- **`ORDER_EXPIRED`** (`actor=SYSTEM`) — graduates from reserved to
  live here, the same transition `OFFER_EXPIRED` made once Revenue
  Agent got its first real confirmation flow: `ORDER_PROPOSED` is now,
  for the first time, a genuine yes/no question, not the pure hand-off
  v0 was.
- An unresolvable clarification reply during cart-building (not a
  final yes/no — `clarify()` can't make sense of the reply at all)
  escalates (`should_escalate=True`, same Escalation Filter path every
  other agent uses) and closes the `PendingAction` as cancelled with no
  `Order` ever created — an abandoned build, not a rejected proposal.

**Known v1 limitation, accepted deliberately**: once a cart is complete
and awaiting the final yes/no, a reply that doesn't match confirm/cancel
(e.g. "actually, add a coke too") falls into Conversation Manager's
existing generic "please confirm with yes or no" clarify path — it
does *not* reopen cart-building. The guest can decline and start a new
order. A combined "edit an already-proposed cart" flow is a reasonable
future enhancement once a pilot shows it's needed, not built
speculatively now, matching this document's own recurring discipline.

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

## 10. Memory Manager — built, see MEMORY_MANAGER.md

This section's original draft (below the line, kept for history)
predates the actual Memory Manager build and is now superseded — in
particular, its "Overwrite" decision rule was explicitly rejected
during that design pass: `dietary_preferences` is never silently
overwritten at any confidence, only appended. **`MEMORY_MANAGER.md`
(repo root) is the authoritative frozen contract** — confidence bands
(≥0.85 auto-apply / 0.70–0.84 hold for staff / <0.70 reject),
field-specific mutation rules, and the `MEMORY_ACCEPTED`/`REJECTED`/
`HELD` Action Ledger taxonomy.

For this document's own purposes: once the order-pattern Guest Memory
track (§9) ships, it produces the same `{field, value, confidence}`
shape the explicit-statement track already does, and Memory Manager
applies it under the exact same rules — no special case for
order-derived evidence.

<details><summary>Original draft (superseded, kept for history)</summary>

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

- **Create**: no existing value for that field, confidence above
  threshold.
- **Merge**: existing value is compatible (e.g. adding "Allergic to
  peanuts" alongside an existing "Vegetarian" — different facts, not a
  conflict).
- **Ignore**: confidence below threshold, or the proposal duplicates
  what's already stored.
- **Overwrite**: existing value present, new proposal contradicts it,
  and confidence clears a *higher* bar than a fresh create would.

</details>

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
- Ask for confirmation before placing any order — enforced by §7: an
  `Order` row only ever comes into existence at `ORDER_CONFIRMED`,
  never before.
- Use only the hotel's uploaded menu and Knowledge Base — same
  structural enforcement as the first bullet.
- **Never claim an item is allergen-safe.** Ordering Agent may *filter*
  recommendations using `Guest.dietary_preferences` (already populated
  by Memory Manager), but has no data source that could honestly
  support an "this is safe for your allergy" assertion — `MenuItem`'s
  own dietary fields (`vegetarian`/`vegan`/`gluten_free`) are the
  hotel's own claims about an item, not a guarantee against
  cross-contamination or an unlisted allergen. A guest stating an
  allergy mid-order still hits the Escalation Filter's existing medical
  pattern first (`escalation_filter.py`, unchanged) — this agent never
  overrides that with its own judgment.

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
- Editing an already-complete, awaiting-confirmation cart (§7.4's known
  v1 limitation — a guest wanting to add an item after the cart was
  proposed declines and starts over, rather than the flow reopening
  cart-building).
- Payment, kitchen integration, automatic staff fulfillment, dynamic
  pricing, LLM-generated menu items, autonomous ingredient
  substitutions, translation, and the order-pattern Guest Memory track
  (§9, stays deferred beyond this design pass).

## 15. Roadmap positioning

§3 (Menu Manager) and this design (§6/§7, Ordering Agent) are no longer
speculative — they're the actual next two roadmap steps, per the
locked sequence: Knowledge Base Editor → Memory Manager → Menu Importer
→ **Ordering Agent** → Translation → Pilot readiness → strategic stop.
Meal reservation (§5) and the order-pattern Guest Memory track (§9)
remain genuinely deferred past that stop, per CONCIERGE.md §0 applied
to the roadmap itself — real pilot conversations, not this document,
should decide whether they're worth building next.

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
4. **`Order` is created only at confirmation, never at proposal**
   (§6/§7.3) — an abandoned or incomplete cart must never look like a
   business transaction in the data Argus eventually learns from.
   "Guest intended to order" and "guest actually ordered" stay
   distinguishable by construction, not by a status filter.
5. **`PendingAction.payload`/`origin_agent` schema extension,
   approved** (§7.1) — generalized, not order-specific: any future
   multi-turn workflow can reuse them. `origin_action_type` becomes
   nullable to represent "cart still being built, no `ActionEvent`
   exists yet."
6. **Conversation Manager's `resolve()` gains a dispatch-back mode**
   (§7.2) — for an incomplete cart, a reply is handed to the
   originating agent's own `clarify()` method (a new, small
   `ClarifiableAgent` protocol) instead of being pattern-matched as
   confirm/cancel. This is the one piece of this design that changes
   Conversation Manager's *behavior*, not just `PendingAction`'s
   *schema* — called out explicitly since CONCIERGE.md §16 is itself a
   frozen contract.
7. **`ORDER_REJECTED` is a new, distinct `action_type`** (§7.4), not a
   reuse of the already-reserved `ORDER_CANCELLED` — "declined before
   ever confirming" and "cancelled after confirming" are different
   events for Argus to learn from. `ORDER_CANCELLED` stays reserved for
   the second case.
8. **The three-way state separation is a named principle, not an
   implementation detail**: `PendingAction` (transient
   conversation/workflow state, disposable) → `Order` (durable
   confirmed business transaction) → `ActionEvent` (immutable
   event/evidence history). Every future multi-turn Concierge
   capability should be checked against this separation before adding
   a new stateful mechanism of its own.
9. **`ConversationManager.register_confirmation_handler`, added during
   Ordering Agent implementation** — a concrete contradiction the
   frozen design didn't resolve: something has to turn a confirmed
   `payload.cart` into real `Order`/`OrderItem` rows on `ORDER_CONFIRMED`,
   but Conversation Manager's own frozen scope (CONCIERGE.md §5.5/§16)
   explicitly forbids it from deciding domain logic. Resolved the same
   way `_clarifiable_agents` already was: a small `{accepted_type:
   handler}` registry, called after the `ActionEvent` is logged and
   before the generic staff `Task` is created. Conversation Manager
   still never inspects what a handler does — `ordering_agent.py`'s own
   `on_order_confirmed` is the one registered today.
10. **`is_food_order` extended to also recognize a named menu item, not
    just v0's hunger phrasing** — exposed by implementation: "Two
    chicken biryani" contains no hunger word at all, so the Intent
    Classifier would never have routed it to Ordering Agent without
    this. Reuses the exact same word-bounded matching `answer()` itself
    uses (`_find_direct_matches`/`_find_ambiguous_group`), so intent
    classification and actual recognition can never drift apart from
    each other — not a second, parallel pattern set.

## 17. Implementation sequence

(1) ✅ `MenuItem` model + migration, (2) ✅ menu upload pipeline (PDF
   path shipped; Excel/CSV deferred per the frozen v1 decision — build
   only if a pilot hotel needs it), (3) ✅ menu editor endpoint, (4) ✅
   Memory Manager (built ahead of this sequence, per the actual roadmap
   order: Knowledge Base Editor → Memory Manager → Menu Importer), (5) ✅
   the design pass (§6/§7 frozen, PR #27) — then, as separate
   implementation PRs, sequenced by persistence-contract-first: (6) ✅
   `PendingAction.payload`/`origin_agent` migration + the
   `ClarifiableAgent` protocol + `Order`/`OrderItem` model (PR #28), (7)
   ✅ Conversation Manager's generic dispatch-back mode, tested against a
   stub `ClarifiableAgent` (PR #29), (8) ✅ Context Builder extension
   (`menu_items`, `order_history` — no `pending_order` field, see §4)
   (PR #30), (9) ✅ Ordering Agent (room service only — meal reservation
   stays deferred per §5, since it additionally needs the Automation
   Engine trigger) — deterministic item/quantity/variant matching
   against `context.menu_items`, never a fuzzy or semantic match, (10)
   ✅ Router integration (the shared `payload["complete"]` convention
   routes an incomplete cart to `start_clarification` instead of the
   normal single-turn proposal path), the `on_order_confirmed`
   snapshot handler registered as a `ConversationManager` confirmation
   handler, tests, CI. (11) order-pattern Guest Memory track stays
   deferred beyond this sequence, per §15 — the roadmap's next step is
   Translation → Pilot readiness, not another agent.
