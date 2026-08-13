# ReVisit Engineering Handbook

## Relationship to ARCHITECTURE.md

`ARCHITECTURE.md` (root) describes a long-term, aspirational target
architecture — including a `backend/modules/{domain}/{models,schemas,
repositories,services,routers,events,tests}/` folder structure that does
**not** match the current codebase, which uses a flatter `app/api`,
`app/models`, `app/services` layout.

Treat ARCHITECTURE.md's **principles** (event-driven, no god services,
AI-as-a-service, tenant isolation, Stripe/Linear/Notion/HubSpot UI
philosophy) as binding — they already match this handbook. Do **not**
reorganize the codebase into its `modules/` folder layout without an
explicit, separate decision to do that migration. Building new features
inside the current flat structure is correct until that decision is made.

## Mission

ReVisit helps businesses turn first-time customers into repeat customers.

Hotels are the first vertical.

We optimize for:

- Repeat customers
- Reviews
- Revenue
- Guest satisfaction
- Operational efficiency

Never optimize for "more AI".

---

## Product Position

ReVisit is an AI-powered Guest Revenue Platform.

AI is an implementation detail.

Always prioritize business outcomes over AI branding.

Avoid excessive use of the word "AI" in the UI.

---

## Tech Stack

Frontend:
- Next.js
- TypeScript
- Tailwind

Backend:
- FastAPI
- SQLAlchemy 2
- PostgreSQL
- Redis

Architecture:
- Multi-tenant
- Event-driven
- Repository pattern
- Domain modules

---

## Coding Standards

- Never duplicate business logic
- Never bypass tenant isolation
- Always use type hints
- Keep business logic out of routes
- Write tests for new features
- Maintain backward compatibility

---

## UI Philosophy

The UI should feel like:

- Stripe
- Linear
- Notion
- HubSpot

Not like an AI demo.

Technology should disappear.

---

## Naming

Prefer:

Guest Intelligence

Insights

Messages

Campaigns

Revenue

Assistant

Suggestions

Avoid unnecessary use of:

AI Messages

AI Revenue

AI Dashboard

AI Guest

AI Analytics

Mention AI only where it represents a true capability.

---

## Product Principles

Every feature must increase at least one:

- Reviews
- Repeat customers
- Revenue
- Guest satisfaction
- Staff efficiency

Otherwise reconsider building it.

---

## Page Completeness Test

Every page must answer three questions, in order:

1. What happened?
2. Why does it matter?
3. What should I do next?

If a page cannot answer all three, it isn't finished — that's a defect,
not a polish item. A page that only shows data (What happened?) without
context (Why does it matter?) or a clear action (What should I do next?)
should be treated the same as a bug.

---

## Architecture

Core Engine

- Guest
- Interaction
- Messaging
- Rewards
- Analytics
- Connectors
- Workflow
- AI Gateway

Verticals

Hotels (Current)

Restaurants

Healthcare

Beauty

Car Rental

Never hardcode hotel logic into the platform core.

---

## Current Status (as of `main @ 19acf91`)

**Pilot Readiness is closed.** Engineering pilot readiness: PASS — 8/8
gates in `PILOT_READINESS.md` §7, each tied to a merged PR and green
CI, not just asserted: production go-live guard, webhook idempotency,
outbound delivery retry, operational monitoring, staff Task completion
evidence, and the shared-WABA WhatsApp architecture
(`WHATSAPP_PLATFORM_ARCHITECTURE.md`).

**Operational pilot validation is pending the first real hotel** —
connecting a real WABA, running a real message round trip, and having
real staff complete a real Task. Do not simulate this with a
developer-owned WhatsApp account.

**Feature development is explicitly stopped.** Do not add a new agent,
guest-facing capability, or AI decision surface without it tracing
back to evidence from a real pilot. If asked to build something new
here, confirm it's justified by real pilot feedback, not "because it's
possible" — that discipline is the whole point of this phase.

---

## Database Schema Changes — Hard Rule

Learned from the PR #52 production incident (2026-08-13): a correct
Alembic migration and a correct SQLAlchemy model still let production
crash-loop for a full day, because production never ran `alembic
upgrade head` — the mechanism that actually patches the live database
was a separate hand-rolled file (`schema_patches.py`) that nobody
updated. Two competing "correct" systems, no shared source of truth,
and nothing caught the gap between them until production was already
crashing. (Issue #53 tracks retiring that dual architecture in favor
of Alembic as the single mechanism — until that's done, both rules
below apply.)

- Any database schema change must include a production migration path
  and a migration test. Never modify an ORM model without verifying
  how the production database receives the corresponding schema
  change.
- Before merging backend changes, inspect deployment configuration,
  migration execution, startup lifecycle, and CI — not just
  application tests.

---

## Before Making Changes

Always:

1. Understand existing architecture
2. Reuse existing components
3. Avoid unnecessary refactoring
4. Explain implementation plan first
5. Keep changes minimal
