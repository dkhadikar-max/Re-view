# Revisit

**An [Argus OS](https://argusai.online) product.**

*Guest revenue, after booking.*

Revisit is the hospitality revenue layer in the Argus decision operating system. V1.0 targets **one paying hotel** with production integrations — not 100 features.

**Parent platform:** [Argus OS](https://argusai.online) · [GitHub](https://github.com/dkhadikar-max/ARGUS-OS)

## For the Argus site

Suggested product blurb when linking from Argus:

> **Revisit** — AI guest revenue after booking. Syncs Cloudbeds, messages guests on WhatsApp/email, drafts review replies, and runs Stripe upsells — with manager approval on every commercial action.

Deep link once deployed: set `NEXT_PUBLIC_ARGUS_SITE_URL` / `ARGUS_SITE_URL` and point Argus at your Revisit production URL.

## Account ownership (who pays / who connects)

| Service | Free? | Paid? | Whose account? |
|---------|-------|-------|----------------|
| GPT-5.5 API | ❌ | ✅ Pay per token | **Yours** (initially) |
| PostgreSQL | ✅ local | ✅ hosted | **Yours** |
| Redis | ✅ local | ✅ hosted | **Yours** |
| Cloudbeds API | ✅ eligible accounts | Included | **Client** |
| Mews API | ✅ eligible accounts | Included | **Client** (roadmap) |
| Guesty API | ✅ eligible accounts | Included | **Client** (roadmap) |
| WhatsApp Business API | ❌ | Meta conversation charges | **Client** |
| Resend | Limited free tier | ✅ | **Client** (preferred) |
| Postmark | Trial | ✅ | **Client** |
| Stripe | No monthly fee | Transaction fees | **Client** |
| Google Business Profile | Free API (quotas) | — | **Client** |

Rule of thumb: **Revisit runs the AI + database**; the hotel connects their PMS, WhatsApp, email, Stripe, and Google.

API: `GET /api/integrations/ownership` and fields on `GET /api/integrations/status`.

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

### Railway deploy

`main` has the full app. Create **two services** from this repo.

**Important:** leave **Root Directory empty** (repo root). Set Dockerfile path instead.

| Service | Builder | Dockerfile path |
|---------|---------|-----------------|
| API | Dockerfile | `backend/Dockerfile` |
| Web | Dockerfile | `frontend/Dockerfile` |

Clear any Custom Build Command (do not use `npm run build` on the API).

API env (minimum): `DATABASE_URL` (Postgres plugin), `REDIS_URL` (optional), `JWT_SECRET`, `ENVIRONMENT=production`, `CORS_ORIGINS`, `ARGUS_SITE_URL=https://argusai.online`, `SEED_ON_STARTUP=true`, `AUTO_CREATE_TABLES=true`.

Web env: `INTERNAL_API_URL=https://<your-api>.up.railway.app`, `NEXT_PUBLIC_ARGUS_SITE_URL=https://argusai.online`.

### Docker (dev)

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
