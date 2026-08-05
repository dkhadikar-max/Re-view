# Re-view

## Project

**Re-view**

## Mission

AI Guest Revenue Agent

## Stack

- Next.js
- FastAPI
- PostgreSQL
- Redis
- GPT-5.5
- n8n

## Architecture

- Event Driven
- Microservices Ready

## Current Sprint

- Authentication
- Reservation Sync
- Guest Memory
- Review Engine

## Status

Planning

---

## Repository Layout

```text
re-view/
├── .cursor/rules/     # Cursor AI rules (architecture, backend, frontend, …)
├── docs/              # PRD, architecture, API, database, prompts
├── backend/           # FastAPI application
├── frontend/          # Next.js dashboard
├── agents/            # AI decision engine
├── connectors/        # PMS / channel integrations
├── workflows/         # Guest lifecycle orchestration
├── infrastructure/    # IaC and deployment
├── docker/            # Local development containers
├── scripts/           # Dev and ops scripts
└── tests/             # Cross-cutting integration tests
```

## Documentation

Read these before writing code:

| Document | Contents |
| --- | --- |
| [docs/PRD.md](./docs/PRD.md) | Vision, users, features, KPIs |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System diagram, services, data flow |
| [docs/ROADMAP.md](./docs/ROADMAP.md) | Milestones, branch strategy, workflow |
| [docs/DATABASE.md](./docs/DATABASE.md) | ER diagrams, tables, indexes |
| [docs/API.md](./docs/API.md) | REST endpoints, webhooks, auth |
| [docs/AI_AGENT.md](./docs/AI_AGENT.md) | Decision engine, Guest Memory |
| [docs/WORKFLOWS.md](./docs/WORKFLOWS.md) | Guest lifecycle stages |
| [docs/PROMPTS.md](./docs/PROMPTS.md) | LLM prompt registry |
| [docs/UI_GUIDELINES.md](./docs/UI_GUIDELINES.md) | Frontend design system |
| [docs/CODING_STANDARDS.md](./docs/CODING_STANDARDS.md) | Lint, test, git conventions |

## Development Workflow

```text
PLAN → Architecture Review → Implementation Plan → Approval → Coding → Testing → Code Review → Refactor → Commit
```

Assign **one milestone at a time**. Review the plan, approve it, then implement.

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

## Cursor Cloud Secrets

Configure in the Cursor Cloud environment (never commit values):

- `OPENAI_API_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `CLERK_SECRET_KEY`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `RESEND_API_KEY`
- `JWT_SECRET`
- `WHATSAPP_API_KEY`
- `STRIPE_SECRET_KEY`

## Milestones

| Sprint | Focus |
| --- | --- |
| **1** | Authentication, PostgreSQL, dashboard shell, multi-tenant foundation |
| **2** | Reservation connectors, guest profiles, event bus |
| **3** | AI Decision Engine, Guest Memory, review workflows |
| **4** | Upsells, analytics, monthly reports |
| **5** | Production hardening, monitoring, billing, marketplace integrations |
