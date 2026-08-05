from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models.entities import (
    Workflow,
    WorkflowRun,
    WorkflowRunStatus,
)
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

ALLOWED_STEPS = {"wait", "ai", "template", "send", "notify", "complete"}


class WorkflowDefinition(BaseModel):
    trigger: str
    steps: list[str] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[str]) -> list[str]:
        for step in steps:
            if step not in ALLOWED_STEPS:
                raise ValueError(f"Unknown workflow step: {step}")
        return steps


def parse_definition(raw: str) -> WorkflowDefinition:
    data = json.loads(raw or "{}")
    return WorkflowDefinition.model_validate(data)


def start_workflow_for_event(
    db: Session,
    *,
    tenant_id: str,
    trigger_event: str,
    event_id: str,
    context: dict[str, Any],
) -> Optional[WorkflowRun]:
    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.tenant_id == tenant_id,
            Workflow.trigger_event == trigger_event,
            Workflow.status == "active",
        )
        .first()
    )
    if not workflow:
        return None

    try:
        definition = parse_definition(workflow.definition)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Invalid workflow definition %s: %s", workflow.id, exc)
        return None

    run = WorkflowRun(
        tenant_id=tenant_id,
        workflow_id=workflow.id,
        trigger_event_id=event_id,
        status=WorkflowRunStatus.running,
        current_step=0,
        context=json.dumps({**context, "definition": definition.model_dump()}),
    )
    db.add(run)
    workflow.runs += 1
    db.flush()
    advance_workflow_run(db, run)
    return run


def advance_workflow_run(db: Session, run: WorkflowRun) -> WorkflowRun:
    ctx = json.loads(run.context or "{}")
    steps = ctx.get("definition", {}).get("steps", [])
    if run.current_step >= len(steps):
        run.status = WorkflowRunStatus.completed
        db.flush()
        return run

    step = steps[run.current_step]
    try:
        if step == "wait":
            run.status = WorkflowRunStatus.waiting
            # Demo: waiting steps complete on next advance/process
            run.current_step += 1
            run.status = WorkflowRunStatus.running
        elif step == "ai":
            ctx["ai_executed"] = True
            run.current_step += 1
        elif step == "template":
            # Zero-cost template agent step (no LLM).
            ctx["template_executed"] = True
            ctx["agent"] = "zero-cost-agent-v1"
            ctx["cost_usd"] = 0.0
            run.current_step += 1
        elif step == "send":
            ctx["send_executed"] = True
            run.current_step += 1
        elif step == "notify":
            ctx["notify_executed"] = True
            run.current_step += 1
        elif step == "complete":
            run.current_step = len(steps)
        else:
            raise ValueError(f"Unsupported step {step}")

        run.context = json.dumps(ctx)
        run.updated_at = datetime.utcnow()
        if run.current_step >= len(steps):
            run.status = WorkflowRunStatus.completed
        db.flush()
    except Exception as exc:  # noqa: BLE001
        run.status = WorkflowRunStatus.failed
        run.error = str(exc)
        db.flush()
    return run


def process_waiting_workflows(db: Session, limit: int = 50) -> int:
    runs = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status.in_([WorkflowRunStatus.waiting, WorkflowRunStatus.running]))
        .limit(limit)
        .all()
    )
    for run in runs:
        if run.status != WorkflowRunStatus.completed:
            advance_workflow_run(db, run)
    return len(runs)


def on_any_event(db: Session, event, payload: dict[str, Any]) -> None:
    start_workflow_for_event(
        db,
        tenant_id=event.tenant_id,
        trigger_event=event.event_type,
        event_id=event.id,
        context=payload,
    )


def register_workflow_handlers() -> None:
    event_bus.subscribe("*", on_any_event)
