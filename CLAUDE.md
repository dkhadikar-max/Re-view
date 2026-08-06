# ReVisit Engineering Handbook

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

## Before Making Changes

Always:

1. Understand existing architecture
2. Reuse existing components
3. Avoid unnecessary refactoring
4. Explain implementation plan first
5. Keep changes minimal
