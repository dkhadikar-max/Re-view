# Guest Revenue Agent (GRA)

**The AI employee that manages every guest after booking.**

Guest Revenue Agent is an AI intelligence layer for hotels. V1.0 targets **one paying hotel** with production integrations — not 100 features.

## V1.0 milestone

| Priority | Integration | Status |
|----------|-------------|--------|
| 1 | **Cloudbeds** — OAuth/API, reservation + guest sync, check-in/out | Adapter + sync (mock or live) |
| 2 | **WhatsApp** — Meta Cloud API, delivery/read, reply → Guest Memory | Adapter + webhooks |
| 3 | **Email** — Resend / Postmark (no custom mail stack) | Adapter |
| 4 | **OpenAI** — AI Gateway → structured JSON → validation → approval | Gateway (never free text) |
| 5 | **Google Reviews** — official Business Profile API only (no scraping) | Adapter + publish path |
| 6 | **Stripe** — upsell payment links → paid webhook → guest memory | Adapter + webhooks |
| 7 | **Analytics** — review rate, repeat guests, revenue, AI msgs, conversion | `/analytics` sales demo |

**Infrastructure:** PostgreSQL (or SQLite locally) + **Redis** job queue + background workers. **No Kafka** until throughput justifies it.

## Celebrate Rewards

Rewards **review participation** (not star rating). Merchant: `/celebrate`. Guest enroll: `/celebrate/<token>`.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js, TypeScript, Tailwind (Fraunces / Outfit) |
| Backend | FastAPI, Python 3.12 |
| Auth | JWT + RBAC |
| Data | SQLite / PostgreSQL + Alembic |
| Queue | Redis (in-memory fallback) |
| AI | AI Gateway → GPT-5.5 (or mock heuristic) → validated JSON |

## Quick start

```bash
# Backend
cd backend
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Demo: `manager@azurecoast.demo` / `ChangeMe123!`

### Docker

```bash
docker compose up --build
```

Includes Redis. Set live keys in `.env` to leave mock mode.

### Tests

```bash
cd backend && PYTHONPATH=. pytest -q
cd frontend && npm run typecheck && npm run build
```

## Key API surfaces

- `GET /api/integrations/status` — V1 readiness board
- `POST /api/connectors/cloudbeds/sync` — reservation/guest sync
- `GET|POST /api/webhooks/whatsapp` — verify + delivery/inbound
- `POST /api/offers/{id}/payment-link` — Stripe Checkout
- `POST /api/webhooks/stripe` — paid → offer accepted + guest memory
- `GET /api/analytics/sales` — sales demo metrics

## Security

- JWT on `/api/*` (except login + public webhooks/celebrate token)
- Tenant from token only
- Approvals required before commercial/low-confidence AI actions
- CORS allowlist, rate limits, audit log

## Honest notes

- Without live API keys, adapters run in **mock** mode (safe for demos/tests).
- Google Reviews never scrapes — empty sync until official OAuth is configured.
- Production deploy + first paying hotel closes V1.0.
