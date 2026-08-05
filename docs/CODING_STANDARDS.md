# Re-view — Coding Standards

**Status:** Planning  
**Last updated:** 2026-08-05

## General

- Prefer clarity over cleverness
- One module, one responsibility
- Document non-obvious decisions in code comments or ADRs under `docs/`
- Never commit secrets — use environment variables (see Cloud secrets list in README)

## Backend (Python / FastAPI)

| Topic | Standard |
| --- | --- |
| Python | 3.12+ |
| Style | Ruff (lint + format) |
| Types | Full type hints; Pydantic v2 for schemas |
| Async | `async def` endpoints; async SQLAlchemy sessions |
| Structure | `api/` → `services/` → `repositories/` → `models/` |
| DI | FastAPI `Depends()` for services and DB sessions |
| Errors | Custom exception hierarchy; map to HTTP in middleware |
| Logging | Structured JSON logs; never log PII or tokens |

### Endpoint checklist

Every endpoint must include:

- Request/response validation (Pydantic)
- Error handling
- Structured logging
- Tests (unit + API)

## Frontend (TypeScript / Next.js)

| Topic | Standard |
| --- | --- |
| Language | TypeScript strict mode |
| Lint | ESLint + Prettier |
| Components | Server Components default; `"use client"` only when needed |
| Data fetching | Server Components or typed API client in `lib/` |
| State | URL state and server data first; client state only for UI |
| Styling | Tailwind utility classes; extract repeated patterns to components |

## Database

- Alembic for all migrations
- UUID primary keys, soft delete, timestamps (see [DATABASE.md](./DATABASE.md))
- Repository pattern — no raw SQL in route handlers

## Testing

| Layer | Tool |
| --- | --- |
| Backend unit | pytest |
| Backend API | pytest + httpx AsyncClient |
| Frontend unit | Vitest |
| Frontend E2E | Playwright (Sprint 2+) |

Never finish a task without tests. Fix linting and formatting before commit.

## Git

- Branch from `develop` for features (`feature/<name>`)
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`
- PR requires passing CI and architecture review for cross-cutting changes

## Security

See `.cursor/rules/security.mdc`:

- RBAC on all mutating endpoints
- Rate limiting on public and webhook routes
- Webhook signature validation
- Input sanitization; parameterized queries only

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- `.cursor/rules/architecture.mdc`
- `.cursor/rules/backend.mdc`
- `.cursor/rules/frontend.mdc`
- `.cursor/rules/testing.mdc`
