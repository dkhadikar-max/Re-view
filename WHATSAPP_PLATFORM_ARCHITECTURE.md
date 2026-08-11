# WhatsApp Platform vs. Property Connection Readiness

**Status: frozen design amendment — no code changes in this document.**
Written after the §6 (PILOT_READINESS.md) real-WhatsApp-verification attempt
surfaced a live-deployment boot failure and an implicit architectural
question underneath it: does ReVisit's WhatsApp integration belong to
the platform, or to each hotel?

## 0. CTO decision (frozen)

**Shared WABA stays. BYO-per-hotel Meta App is deferred, not adopted.**

ReVisit acts as the WhatsApp platform/BSP layer — one ReVisit-owned Meta
App/WABA, one platform-level access token that can send through any
phone number registered under it. Each hotel's channel is identified by
`Property.whatsapp_phone_number_id`, not by a separate set of hotel-owned
credentials. This is already how the code is built
(`integrations/whatsapp.py`, CONCIERGE.md §3) — this document confirms
that as the deliberate, continuing direction rather than reversing it,
and fixes the one place where the deployment-readiness check didn't yet
reflect a multi-property product.

Rejected alternative (BYO-per-hotel): every hotel creates its own Meta
Developer account, completes Business verification, generates its own
token/app secret, and configures its own webhook. Real architecture,
disproportionate cost for a managed-platform onboarding experience —
introduces encrypted per-tenant credential storage, credential rotation,
tenant-scoped secret resolution, and a webhook signature-verification
ordering change (verify-before-parse becomes parse-to-identify-tenant-
then-verify). Not necessary to prove the core product. Revisit only if
a specific hotel's compliance requirements demand it.

## 1. The three layers (frozen)

**Platform-level** (global, `Settings`, unchanged by this doc):
- Meta App, WABA
- `whatsapp_access_token`, `whatsapp_app_secret`, `whatsapp_verify_token`
- `WhatsAppCloudClient` (`app/integrations/whatsapp.py`)

**Property-level** (per-tenant, this doc adds one field):
- `whatsapp_phone_number_id` (already exists)
- `whatsapp_connection_status` (**new** — see §3)
- tenant/property association (already exists via `Property.tenant_id`)

**Runtime** (already built, unchanged):
```
Meta webhook
     ↓
verify platform signature   (whatsapp_app_secret — one secret, checked first)
     ↓
identify phone_number_id    (value.metadata.phone_number_id)
     ↓
resolve Property            (Property.whatsapp_phone_number_id lookup)
     ↓
resolve tenant               (Property.tenant_id)
     ↓
process message
     ↓
send using property's phone_number_id + platform-level access token
```

## 2. The actual flaw, precisely stated

PR #39's go-live guard (`reject_mock_mode_in_production`,
`app/core/config.py`) checks exactly one condition for WhatsApp:
`whatsapp_access_token` (a platform-level setting) is non-empty. It does
**not** inspect any `Property` row and never has — so the guard was
already, accidentally, a pure platform-level check; it just wasn't
*documented* as one, and nothing else in the system distinguishes "the
platform has no real WhatsApp integration at all" from "the platform is
correctly configured but no hotel has connected a number yet." Today
those two states can't even be told apart, because `Property` has no
notion of connection status beyond the implicit
`whatsapp_phone_number_id IS NOT NULL`.

So the guard's boot condition does not need to change. What's missing:

1. **No explicit statement, anywhere, that the guard is platform-only** —
   the error message and the docstring should say so directly, so a
   future edit doesn't "fix" it into a per-property check by mistake.
2. **No test proving** `production + real platform token + zero
   connected properties` boots successfully — the exact case that
   caused hesitation about whether this needed a design review at all.
3. **No explicit `Property` connection-state field** — onboarding a
   hotel today is "type a `phone_number_id` into a text field," with no
   way to represent "not connected yet" vs. "connected" vs. "was
   connected, now disabled" as a first-class state a hotel-onboarding
   UI (or a future health check) can reason about.

## 3. What this doc actually changes

- **`app/core/config.py`**: no change to the boot *condition*. Docstring
  and the raised error's wording get an explicit "this is a
  platform-level check, independent of any property's connection
  state" statement, so the invariant survives future edits.
- **New test**: production settings with a real platform token and zero
  `Property` rows carrying `whatsapp_phone_number_id` must construct
  `Settings()` successfully — proving §0's second invariant
  (`production + real platform integration + zero connected properties
  = boot`) holds, not just asserting it in prose.
- **`Property.whatsapp_connection_status`** (new column): a small closed
  enum — `not_connected` (default) / `connected` — set to `connected`
  when `whatsapp_phone_number_id` is set, `not_connected` otherwise, for
  v1. Nullable-free, defaults closed. This is deliberately **not** a
  richer health-check state (token still valid, number not disconnected
  by Meta, etc.) — that's "individual property readiness," explicitly
  out of scope here (§4).

## 4. Explicit non-goals (deferred, not forgotten)

- Per-property WhatsApp credentials (BYO Meta App) — §0.
- Credential rotation, secret access controls, encrypted per-tenant
  secret storage — only relevant if BYO is ever adopted.
- Property-level *health* monitoring (token validity, number connection
  drift, Meta-side disablement) — a real feature, but a different one
  than "does this property have a phone_number_id at all."
- Any onboarding UI/embedded-signup automation — connecting a property
  today stays "ReVisit ops sets `whatsapp_phone_number_id` via the
  existing Property settings field"; automating that flow is separate
  product work.
- Re-running §6's real-WhatsApp-verification sequence — happens
  naturally the next time an actual hotel connects a number, not before.

## 5. Acceptance criteria

- [ ] `reject_mock_mode_in_production`'s docstring and raised-error text
      explicitly state the check is platform-level only.
- [ ] New test: `production` + real platform WhatsApp token + zero
      `Property` rows with `whatsapp_phone_number_id` set →
      `Settings()` constructs without error.
- [ ] Existing go-live guard tests (9 from PR #39) still pass unchanged
      — this is additive, not a behavior change to the existing checks.
- [ ] `Property.whatsapp_connection_status` column + migration, default
      `not_connected`, backfilled to `connected` for any existing row
      that already has a non-null `whatsapp_phone_number_id`.
- [ ] `PropertyUpdate`/property-settings endpoint keeps
      `whatsapp_connection_status` in sync when
      `whatsapp_phone_number_id` is set or cleared (connecting a number
      sets `connected`; clearing it sets `not_connected`).
- [ ] Full regression suite green, targeted tests green, CI green —
      same bar as every other PILOT_READINESS.md item this session.
