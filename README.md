# Guest Revenue Agent (GRA)

**The AI employee that manages every guest after booking.**

Guest Revenue Agent is an AI intelligence layer for hotels, resorts, and vacation rentals. It sits above your existing PMS/CRM stack and autonomously manages the post-booking guest journey — messaging, reviews, upsells, and lifetime value — without replacing your current systems.

## Celebrate Rewards

**Tagline:** Turn verified reviewers into repeat customers.

Rewards **review participation** (not star rating). After a verified review, guests unlock birthday/anniversary offers, confirm immutable dates, receive coupons, and get automated celebration campaigns.

- Merchant settings: `/celebrate` (discount, window, min spend, stackable)
- Guest enrollment link: `/celebrate/<token>`
- Super Admin only can unlock dates (reason + audit required)
- Nightly campaigns via **Run nightly campaigns** or `POST /api/workers/tick`

## Phase 1 (hardened)

- JWT auth + RBAC (viewer/staff/manager/admin)
- Tenant isolation on every query/mutation
- PMS sync simulation (Cloudbeds) + validated CSV import
- Guest Memory profiles (LTV, preferences, satisfaction)
- Event outbox + workflow runner
- AI decision provider interface with JSON schema validation
- Multilingual messaging with delivery worker
- Automated review requests + AI draft responses
- Negative review escalation
- Approval workflow (AI cannot bypass gates)
- Audit logging + structured request logs
- Operations & revenue dashboard
- Pytest suite + GitHub Actions CI

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Auth | JWT (HS256) + bcrypt |
| Database | SQLite (local) / PostgreSQL-ready + Alembic |
| AI | Heuristic provider (default) or OpenAI-mode adapter |
| Events | Transactional outbox (Redis Streams later) |

## Quick start

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env   # optional
uvicorn app.main:app --reload --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health
- Ready: http://127.0.0.1:8000/ready

Demo login: `manager@azurecoast.demo` / `ChangeMe123!`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:3000/login

### Docker (dev)

```bash
docker compose up --build
```

Browser traffic uses same-origin `/api` rewrites to the backend service (`INTERNAL_API_URL`).

### Tests

```bash
cd backend && pytest -q
cd frontend && npm run typecheck && npm run build
```

### Migrations

```bash
cd backend
alembic upgrade head
# or generate: alembic revision --autogenerate -m "change"
```

## Security model

- All `/api/*` routes (except login) require `Authorization: Bearer <jwt>`
- Tenant ID is taken from the token — never from the client body
- Mutations require `staff` or `manager` role
- Approvals set `reviewed_by` from the authenticated user
- Messages in `pending_approval` cannot be sent until approved (then queued for delivery)
- CORS is an explicit allowlist (no `*`)
- Rate limiting, request IDs, and security headers are enabled

## Architecture

```
Booking channels → PMS connector → Event outbox
  → AI Decision (validated JSON) → Approval / Queue
  → Messaging worker → Audit log → Dashboard
```

AI never executes unchecked commercial or low-confidence actions.

## Project layout

```
backend/
  app/
    api/routes.py
    core/          # config, security, middleware, logging
    models/
    services/      # AI, events, workflows, messaging, connectors, audit
    db/            # session, seed
  alembic/
  tests/
frontend/
  src/app/         # dashboard pages + /login
  src/lib/api.ts   # authenticated API client
```

## Honest capability notes

| Capability | Status |
|------------|--------|
| Auth / tenancy / approvals / audit | Implemented |
| Event outbox + workers | Implemented (in-process tick) |
| Workflow runner | Implemented (validated step machine) |
| AI provider | Heuristic default; OpenAI adapter stub when key set |
| Cloudbeds / WhatsApp / Email | Simulated adapters with sealed config storage |
| Redis / Kafka | Not yet — swap event bus later |
