# Re-view — Roadmap

**Status:** Planning  
**Last updated:** 2026-08-05

## Branch Strategy

```text
main
develop
feature/auth
feature/dashboard
feature/guest-memory
feature/review-engine
feature/workflow
feature/connectors
feature/analytics
```

## Milestones

### Sprint 1 — Foundation

- [ ] Authentication (Clerk integration, JWT, RBAC)
- [ ] PostgreSQL schema and Alembic migrations
- [ ] Multi-tenant foundation (organizations, properties)
- [ ] Dashboard shell (Next.js, dark mode, layout)
- [ ] CI: lint, format, test gates

### Sprint 2 — Data & Events

- [ ] Reservation connectors (webhook + sync framework)
- [ ] Guest profiles and Guest Memory schema
- [ ] Event bus (Redis streams or equivalent)
- [ ] Connector abstraction layer

### Sprint 3 — AI Core

- [ ] AI Decision Engine (structured JSON only)
- [ ] Context builder
- [ ] Prompt registry (`docs/PROMPTS.md`)
- [ ] Review workflows (request, remind, thank)
- [ ] Audit log for every AI decision

### Sprint 4 — Revenue

- [ ] Upsell engine and offer templates
- [ ] Analytics dashboards
- [ ] Monthly performance reports

### Sprint 5 — Production

- [ ] Production hardening (rate limits, monitoring, alerts)
- [ ] Billing (Stripe)
- [ ] Marketplace / third-party integrations

## Current Sprint

**Sprint 1** — Authentication, PostgreSQL, Dashboard shell, Multi-tenant foundation

## Development Workflow

Every feature follows:

```text
PLAN → Architecture Review → Implementation Plan → Approval → Coding → Testing → Code Review → Refactor → Commit
```

## How to Use Cursor

Do not ask Cursor to "build Re-view" in one pass. Treat Cursor as your engineering team:

1. Assign **one milestone** at a time
2. Require a plan and wait for approval
3. Implement, test, and review before the next milestone

## Initial Architect Prompt

Use this before any implementation:

```text
You are the Principal Software Architect for Re-view.

Mission:
Build an enterprise-grade AI Guest Revenue Agent.

Before writing any code:
1. Read every document inside docs/.
2. Review the repository.
3. Understand the architecture.
4. Identify missing pieces.
5. Produce an implementation roadmap.
6. Break the project into milestones.
7. List every module.
8. List every dependency.
9. Wait for my approval.

Do NOT write code.
```
