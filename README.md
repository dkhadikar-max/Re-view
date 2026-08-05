# Guest Revenue Agent (GRA)

**The AI employee that manages every guest after booking.**

Guest Revenue Agent is an AI intelligence layer for hotels, resorts, and vacation rentals. It sits above your existing PMS/CRM stack and autonomously manages the post-booking guest journey — messaging, reviews, upsells, and lifetime value — without replacing your current systems.

## Phase 1 MVP

- PMS sync simulation (Cloudbeds) + CSV import
- Guest Memory profiles (LTV, preferences, satisfaction)
- Event-driven AI Decision Engine
- Multilingual messaging (WhatsApp / Email / SMS)
- Automated review requests + AI draft responses
- Negative review escalation
- Upsell offers
- Approval workflow (AI never executes unchecked)
- Operations & revenue dashboard
- Review intelligence themes

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Database | SQLite (MVP) / PostgreSQL-ready |
| AI | Heuristic orchestrator (swap in GPT via `OPENAI_API_KEY`) |
| Events | In-process event bus (Redis Streams later) |

## Quick start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs  
Health: http://127.0.0.1:8000/health

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:3000

### Docker

```bash
docker compose up --build
```

## Demo property

Seeded as **Azure Coast Resort** (Nice, France) with guests, reservations, messages, reviews, offers, approvals, and workflows.

Useful demo actions:

1. **Operations** — approve pending messages
2. **Reservations** — create a reservation (triggers AI) or run **AI decide**
3. **Settings** — **Sync Cloudbeds** to import new reservations
4. **Reviews** — publish AI draft responses for negative reviews
5. **Intelligence** — theme extraction from reviews

## Architecture

```
Booking channels → PMS → Guest Revenue Agent
  AI Brain · Guest Memory · Decision Engine
  Workflow Engine · Review Engine · Revenue Engine
         ↓
WhatsApp · Email · SMS · Google · Stripe · Dashboard
```

Core principle: everything is event-driven.

```
Reservation Created → AI Thinks → Decides → Acts → Learns
```

AI output is always validated JSON. Actions requiring low confidence or commercial impact go through the **Approval Queue**.

## API highlights

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/dashboard/stats` | Ops + revenue KPIs |
| GET/POST | `/api/reservations` | List / create (emits events) |
| POST | `/api/reservations/{id}/decide` | Run AI decision engine |
| GET/POST | `/api/approvals/{id}` | Approve or reject AI actions |
| POST | `/api/connectors/sync` | Simulate PMS pull |
| POST | `/api/connectors/import-csv` | CSV reservation import |
| GET | `/api/intelligence` | Review theme report |

## Project layout

```
backend/
  app/
    api/routes.py          # REST API
    models/entities.py     # Core tables
    services/
      ai_orchestrator.py   # Decision + messaging + review AI
      event_bus.py         # Event bus
    db/seed.py             # Demo data
frontend/
  src/app/                 # Dashboard pages
```

## Roadmap

- **Phase 2** — deeper guest memory, offer engine, revenue analytics, segmentation
- **Phase 3** — LTV prediction, multi-property, AI concierge, CRM integrations

## Positioning

Most competitors optimize reviews. GRA optimizes **guest lifetime value**.
