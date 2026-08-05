from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.services.ai_orchestrator import AIDecisionSchema, HeuristicAIProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Revisit, the AI Guest Operating System for a hotel (an Argus OS product).
You decide the next best guest action: welcome, upsell, review request, recovery, or celebrate reward.
Be warm, specific, and never pushy. Prefer WhatsApp when the guest prefers it.
Always leave commercial sends for human approval when confidence is uncertain.
Return ONLY valid JSON matching this schema:
{
  "action": "Welcome" | "Upsell" | "ReviewRequest" | "None",
  "channel": "whatsapp" | "email" | "sms",
  "language": "en|de|fr|es|it|pt|nl",
  "timing": "string",
  "offer": "string or null",
  "confidence": 0.0-1.0,
  "reasoning": "string",
  "execute_at": "ISO-8601 datetime or null"
}
Never return free text. Never invent offers outside the provided catalog.
Never execute actions — only decide.
"""


class AIGateway:
    """AI Gateway → model → structured JSON → validation.

    Never returns free text to callers. Always validated JSON.
    """

    def __init__(self) -> None:
        self.model = settings.openai_model
        self.api_key = settings.openai_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and not settings.use_mock_ai

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            # Deterministic heuristic still returns schema-valid JSON path
            from app.models.entities import Guest, Property, Reservation

            # context may contain plain dicts from callers
            return HeuristicAIProvider().decide(
                _Obj(context["guest"]),
                _Obj(context["reservation"]),
                _Obj(context["property"]),
                context.get("extra"),
            )

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(context, default=str),
                    },
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or "{}"
            raw = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            logger.exception("OpenAI gateway failed; falling back to heuristic: %s", exc)
            return HeuristicAIProvider().decide(
                _Obj(context["guest"]),
                _Obj(context["reservation"]),
                _Obj(context["property"]),
                context.get("extra"),
            )

        try:
            validated = AIDecisionSchema.model_validate(raw)
            return validated.model_dump(mode="json")
        except ValidationError as exc:
            logger.warning("AI JSON failed validation: %s", exc)
            raise


class _Obj:
    """Tiny attribute proxy so heuristic provider can read dict-like context."""

    def __init__(self, data: dict[str, Any]):
        self.__dict__.update(data)


ai_gateway = AIGateway()
