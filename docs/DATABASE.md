# Re-view — Database

**Status:** Planning  
**Last updated:** 2026-08-05

## Conventions

- **PostgreSQL** as the system of record
- **UUID** primary keys on all tables
- **Soft delete** via `deleted_at` (nullable timestamp)
- **Timestamps** — `created_at`, `updated_at` on every table
- **Indexes** on foreign keys and common query patterns
- **Foreign keys** enforced at the database level
- Normalize first; denormalize only with documented justification
- All schema changes via **Alembic** migrations

## Entity Relationship (Planning)

```mermaid
erDiagram
    organizations ||--o{ properties : owns
    properties ||--o{ units : contains
    properties ||--o{ reservations : hosts
    guests ||--o{ reservations : books
    guests ||--o{ guest_memories : has
    reservations ||--o{ workflow_runs : triggers
    workflow_runs ||--o{ ai_decisions : produces
    guests ||--o{ reviews : writes
    guests ||--o{ upsell_offers : receives
    organizations ||--o{ users : employs

    organizations {
        uuid id PK
        string name
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }

    properties {
        uuid id PK
        uuid organization_id FK
        string name
        string timezone
        jsonb settings
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }

    guests {
        uuid id PK
        string email
        string phone
        string full_name
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }

    guest_memories {
        uuid id PK
        uuid guest_id FK
        uuid property_id FK
        jsonb preferences
        jsonb stay_history
        jsonb sentiment
        timestamp created_at
        timestamp updated_at
    }

    reservations {
        uuid id PK
        uuid property_id FK
        uuid guest_id FK
        string external_id
        date check_in
        date check_out
        string status
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }

    workflow_runs {
        uuid id PK
        uuid reservation_id FK
        string stage
        string status
        timestamp created_at
        timestamp updated_at
    }

    ai_decisions {
        uuid id PK
        uuid workflow_run_id FK
        string prompt_version
        jsonb input_context
        jsonb output_json
        string validation_status
        timestamp created_at
    }

    reviews {
        uuid id PK
        uuid guest_id FK
        uuid reservation_id FK
        int rating
        text content
        string platform
        timestamp created_at
        timestamp updated_at
    }

    upsell_offers {
        uuid id PK
        uuid guest_id FK
        uuid reservation_id FK
        string offer_type
        decimal amount
        string status
        timestamp created_at
        timestamp updated_at
    }
```

## Tables (Summary)

| Table | Purpose |
| --- | --- |
| `organizations` | Multi-tenant root |
| `users` | Operator accounts (linked to Clerk) |
| `properties` | Hotels, STRs, portfolios |
| `units` | Rooms / listings within a property |
| `guests` | Guest identity across stays |
| `guest_memories` | Preferences, history, AI context |
| `reservations` | Stays synced from PMS/connectors |
| `workflow_runs` | Lifecycle stage tracking |
| `ai_decisions` | Immutable audit of LLM outputs |
| `reviews` | Captured or synced reviews |
| `upsell_offers` | Generated and accepted offers |
| `connector_sync_logs` | Ingestion audit trail |

## Indexes (Planned)

| Table | Index | Rationale |
| --- | --- | --- |
| `reservations` | `(property_id, check_in)` | Calendar and workflow queries |
| `reservations` | `(external_id, property_id)` UNIQUE | Idempotent connector sync |
| `guest_memories` | `(guest_id, property_id)` | Context builder lookup |
| `ai_decisions` | `(workflow_run_id, created_at)` | Audit and debugging |
| `workflow_runs` | `(reservation_id, stage)` | Stage transitions |

## Migration Policy

1. One Alembic revision per logical schema change
2. Migrations must be reversible where feasible
3. No manual production DDL outside migrations
4. Seed data lives in `scripts/`, not migrations

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- `.cursor/rules/database.mdc`
