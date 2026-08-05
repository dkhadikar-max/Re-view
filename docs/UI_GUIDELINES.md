# Re-view — UI Guidelines

**Status:** Planning  
**Last updated:** 2026-08-05

## Design System

- **Framework:** Next.js App Router
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui
- **Theme:** Dark mode by default; light mode optional
- **Icons:** Lucide (via shadcn/ui)

## Principles

1. **Reusable components only** — no copy-pasted UI blocks
2. **Server Components by default** — client components only for interactivity
3. **No business logic in components** — fetch and mutate via API layer / server actions
4. **Accessibility first** — WCAG 2.1 AA minimum (keyboard nav, focus states, ARIA labels)
5. **Responsive** — mobile-friendly operator workflows

## Layout

| Area | Purpose |
| --- | --- |
| **Sidebar** | Primary navigation (Dashboard, Reservations, Guests, Reviews, Upsells, Settings) |
| **Top bar** | Org/property switcher, user menu, notifications |
| **Main content** | Page-specific views |
| **Detail panels** | Guest Memory, workflow timeline, AI decision audit |

## Typography

- Headings: `font-semibold`, clear hierarchy (`text-2xl` → `text-sm`)
- Body: `text-sm` / `text-base`, `text-muted-foreground` for secondary copy
- Monospace: AI JSON audit views, API IDs

## Color (Dark Default)

| Token | Usage |
| --- | --- |
| `background` | Page background |
| `card` | Elevated surfaces |
| `primary` | CTAs, active nav |
| `destructive` | Errors, irreversible actions |
| `muted` | Secondary text, borders |

Use semantic tokens from shadcn/ui theme — never hardcode hex values in components.

## Component Patterns

### Data tables

- Sortable columns where applicable
- Empty states with clear next action
- Loading skeletons, not spinners alone

### Forms

- Inline validation with accessible error messages
- Destructive actions require confirmation dialog

### AI audit views

- Syntax-highlighted JSON (read-only)
- Show `prompt_version`, `validation_status`, timestamp
- Link to related reservation and guest

## File Structure

```text
frontend/
├── app/              # Routes (App Router)
├── components/
│   ├── ui/           # shadcn primitives
│   └── ...           # Domain components
├── lib/              # API client, utils
└── styles/           # Global CSS
```

## References

- `.cursor/rules/frontend.mdc`
- [ARCHITECTURE.md](./ARCHITECTURE.md)
