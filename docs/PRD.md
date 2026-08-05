# Re-view — Product Requirements Document

**Status:** Planning  
**Last updated:** 2026-08-05

## Vision

Re-view is an enterprise-grade **AI Guest Revenue Agent** for hospitality operators. It orchestrates the full guest lifecycle—from reservation through checkout—to maximize revenue, reviews, repeat bookings, and guest satisfaction through intelligent, timely, and personalized automation.

## Users

| Persona | Goals |
| --- | --- |
| **Property operator / GM** | Increase RevPAR, review scores, and direct bookings; reduce manual guest communication |
| **Front desk / concierge** | Hand off routine guest messaging to AI while retaining override control |
| **Revenue manager** | Surface upsell opportunities and measure campaign performance |
| **Guest** | Seamless stay experience, relevant offers, easy review and rebooking |

## Features

### Core (MVP)

- Multi-tenant authentication and organization management
- Property and unit configuration
- Reservation sync from PMS/channel connectors
- Guest profiles and **Guest Memory** (preferences, history, sentiment)
- Event-driven workflow engine (reservation → check-in → stay → checkout → review → upsell → repeat)
- AI Decision Engine with structured JSON outputs and audit logs
- Review request and response workflows
- Operator dashboard shell

### Growth

- Upsell engine (late checkout, upgrades, amenities, experiences)
- Analytics and monthly performance reports
- Marketplace / connector integrations
- Billing and subscription management

## KPIs

| Metric | Target (initial) |
| --- | --- |
| Review response rate | ≥ 40% of eligible stays |
| Average review rating uplift | +0.3 stars within 90 days |
| Upsell conversion | ≥ 8% of offered upsells |
| Repeat booking rate | +15% vs. baseline |
| AI decision audit coverage | 100% of automated actions logged |
| API p99 latency | < 500ms (excluding LLM calls) |
| System uptime | 99.5% |

## Non-Goals (Planning Phase)

- Direct LLM execution of side effects without validation
- Monolithic all-in-one deployment
- Hardcoded secrets or tenant data in source control

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ROADMAP.md](./ROADMAP.md)
- [WORKFLOWS.md](./WORKFLOWS.md)
