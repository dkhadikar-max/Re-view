# Re-view — Workflows

**Status:** Planning  
**Last updated:** 2026-08-05

## Guest Lifecycle

```text
Reservation
    ↓
Check-in
    ↓
Stay
    ↓
Checkout
    ↓
Review
    ↓
Upsell
    ↓
Repeat booking
```

## Stages

| Stage | Trigger | Typical Actions |
| --- | --- | --- |
| **Reservation** | Connector sync / webhook | Create guest profile, seed Guest Memory, schedule pre-arrival |
| **Pre-arrival** | T-48h before check-in | Welcome message, arrival instructions, upsell early check-in |
| **Check-in** | PMS event or manual | Confirm arrival, offer amenities |
| **Stay** | Mid-stay timer | Satisfaction check, service offers |
| **Checkout** | PMS checkout event | Thank you, receipt, review prep |
| **Review** | T+24h post-checkout | Review request, reminder, thank-you on response |
| **Upsell** | Post-review or mid-stay | Late checkout, upgrade, experience packages |
| **Repeat booking** | High sentiment + history | Direct booking offer, loyalty message |

## Event Bus

Domain events drive stage transitions. Producers emit; Workflow Orchestrator consumes.

| Event | Producer | Consumer |
| --- | --- | --- |
| `reservation.created` | Connectors | Workflow Orchestrator |
| `reservation.updated` | Connectors | Workflow Orchestrator |
| `guest.checked_in` | Connectors / manual | Workflow Orchestrator |
| `guest.checked_out` | Connectors / manual | Workflow Orchestrator |
| `ai.decision.made` | Decision Engine | Action Executor |
| `message.sent` | Action Executor | Analytics |
| `review.received` | Webhook / manual | Guest Memory, Analytics |
| `upsell.accepted` | Stripe / manual | Analytics, Billing |

## Workflow Orchestrator

Location: `workflows/`

Responsibilities:

- Track `workflow_runs` per reservation
- Enforce stage ordering and idempotency
- Invoke Context Builder + Decision Engine at decision points
- Respect quiet hours and property policies
- Integrate with n8n for external automations where configured

## n8n Integration

n8n handles:

- Long-running timers (e.g., review reminder at T+72h)
- Third-party integrations without custom code
- Operator-defined automation overrides

Re-view core remains the source of truth for guest state and AI decisions.

## Idempotency

- Each stage transition keyed by `(reservation_id, stage, event_id)`
- Duplicate webhook delivery must not double-send messages
- AI decisions reference `workflow_run_id` for traceability

## References

- [AI_AGENT.md](./AI_AGENT.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [API.md](./API.md)
