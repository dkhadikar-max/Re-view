# Re-view — AI Agent

**Status:** Planning  
**Last updated:** 2026-08-05

## Principles

1. **Never** let the LLM execute actions directly
2. LLM returns **structured JSON** validated against a schema
3. All prompts sourced from [PROMPTS.md](./PROMPTS.md)
4. Every decision stored in `ai_decisions` with full audit trail
5. API keys only via environment variables

## Decision Engine

The Decision Engine selects the next best action for a guest lifecycle event.

### Input

- Workflow stage (`pre_arrival`, `check_in`, `mid_stay`, `checkout`, `post_stay`, `review`, `upsell`, `rebook`)
- Guest Memory snapshot
- Property settings and policies
- Reservation details
- Recent interaction history

### Output (JSON Schema — illustrative)

```json
{
  "action": "send_message",
  "channel": "email",
  "template_id": "pre_arrival_welcome",
  "personalization": {
    "guest_name": "Jane",
    "check_in_time": "3:00 PM"
  },
  "confidence": 0.92,
  "reasoning_summary": "First-time guest, no prior preferences on file.",
  "requires_human_approval": false
}
```

Allowed `action` values (extensible via config):

- `send_message`
- `request_review`
- `offer_upsell`
- `wait`
- `escalate_to_human`
- `no_action`

### Validation Pipeline

```
LLM response → JSON parse → Pydantic schema → business rules → audit persist → action executor (if approved)
```

If validation fails: log failure, escalate or fall back to `no_action`. Never execute unvalidated output.

## Guest Memory

Guest Memory is the persistent context layer for personalization.

| Field | Source | Use |
| --- | --- | --- |
| `preferences` | Stated + inferred | Tone, language, channel preference |
| `stay_history` | Reservations | Repeat guest detection |
| `sentiment` | Reviews + messages | Risk / delight signals |
| `interaction_log` | Workflow events | Avoid duplicate outreach |

Context Builder merges Guest Memory with reservation and property data into a bounded token payload for the LLM.

## Context Builder

Responsibilities:

- Fetch guest, reservation, property, and recent decisions
- Redact PII not required for the current prompt
- Enforce max context size
- Attach prompt version identifier for reproducibility

## Prompt Flow

```text
Event received
  → Load prompt template (docs/PROMPTS.md + version)
  → Context Builder assembles variables
  → LLM call (GPT-5.5, structured output mode)
  → Validate JSON
  → Persist ai_decisions row
  → Emit domain event for workflow continuation
```

## Audit Requirements

Every `ai_decisions` record must include:

- `workflow_run_id`
- `prompt_version`
- `input_context` (redacted where required)
- `output_json` (raw LLM output)
- `validation_status` (`passed` | `failed`)
- `created_at`

## Human-in-the-Loop

When `requires_human_approval` is true or confidence is below threshold:

- Queue action for operator review in dashboard
- Do not send messages or create charges until approved

## References

- [PROMPTS.md](./PROMPTS.md)
- [WORKFLOWS.md](./WORKFLOWS.md)
- `.cursor/rules/ai.mdc`
