# Re-view — API

**Status:** Planning  
**Last updated:** 2026-08-05

## Base URL

| Environment | URL |
| --- | --- |
| Local | `http://localhost:8000` |
| Production | TBD |

## Authentication

- **Operators:** Clerk session → JWT validated by FastAPI middleware
- **Service-to-service:** Internal API keys (environment variables)
- **Webhooks:** HMAC signature validation per connector

### Headers

```http
Authorization: Bearer <jwt>
X-Organization-Id: <uuid>
Content-Type: application/json
```

## REST Endpoints (Planned)

### Health

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Readiness (DB + Redis) |

### Organizations & Properties

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/organizations/me` | Current org context |
| `GET` | `/api/v1/properties` | List properties |
| `POST` | `/api/v1/properties` | Create property |
| `GET` | `/api/v1/properties/{id}` | Property detail |

### Reservations

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/reservations` | List (filter by property, dates) |
| `GET` | `/api/v1/reservations/{id}` | Reservation detail |
| `POST` | `/api/v1/reservations/sync` | Trigger manual sync |

### Guests

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/guests/{id}` | Guest profile |
| `GET` | `/api/v1/guests/{id}/memory` | Guest Memory context |

### Workflows

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/workflows/runs` | List workflow runs |
| `POST` | `/api/v1/workflows/runs/{id}/advance` | Manual stage advance (RBAC) |

### Reviews

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/reviews` | List reviews |
| `POST` | `/api/v1/reviews/request` | Trigger review request |

### Upsells

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/upsells` | List offers |
| `POST` | `/api/v1/upsells` | Create offer |

### AI (Internal)

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/v1/ai/decide` | Run decision engine (structured JSON) |
| `GET` | `/api/v1/ai/decisions` | Audit log query |

## Webhook Contracts

### Inbound — Reservation Sync

```http
POST /webhooks/connectors/{connector_id}/reservations
X-Webhook-Signature: sha256=<hmac>
```

```json
{
  "event": "reservation.created",
  "external_id": "pms-12345",
  "property_external_id": "prop-99",
  "guest": {
    "email": "guest@example.com",
    "full_name": "Jane Guest",
    "phone": "+15551234567"
  },
  "check_in": "2026-09-01",
  "check_out": "2026-09-05",
  "status": "confirmed"
}
```

### Outbound — Workflow Events (n8n)

Events published to Redis streams or HTTP callbacks:

- `reservation.created`
- `guest.checked_in`
- `guest.checked_out`
- `review.requested`
- `review.received`
- `upsell.offered`
- `upsell.accepted`

## Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": []
  }
}
```

| HTTP Status | Usage |
| --- | --- |
| `400` | Validation failure |
| `401` | Unauthenticated |
| `403` | Forbidden (RBAC) |
| `404` | Resource not found |
| `429` | Rate limited |
| `500` | Internal error |

## Examples

### Get guest memory

```bash
curl -s http://localhost:8000/api/v1/guests/{guest_id}/memory \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-Id: $ORG_ID"
```

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [AI_AGENT.md](./AI_AGENT.md)
- `.cursor/rules/backend.mdc`
