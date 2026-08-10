"""Translation provider client — TRANSLATION_LAYER.md.

    translation_client.detect_language(text) -> str
    translation_client.translate(text, *, source_language, target_language) -> str

Follows the same `configured`/`mode` convention as `WhatsAppCloudClient`
(`whatsapp.py`) and `AIGateway` (`openai_gateway.py`): a deterministic
mock fallback when no provider credential is configured, so tests and
local dev never require a live API key or network access.

This module owns exactly two operations — detecting a language and
translating text between two languages — and nothing else. Per
TRANSLATION_LAYER.md §0 ("an I/O normalization layer, not an
intelligence layer") and the CTO's own boundary diagram:

    Translation:  String -> String
    Concierge:    structured input -> structured decision
    Translation:  String -> String

Every public method here takes plain text and returns plain text (or
raises). Nothing in this module ever sees, accepts, or returns an
`Order`, `PendingAction`, `ActionEvent`, `correlation_id`, confidence
score, or any other structured Concierge object — that boundary is kept
mechanically obvious by this module's own type signatures, not just by
convention.
"""

from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# The Concierge pipeline's canonical internal language (TRANSLATION_
# LAYER.md §0/§3) — every call site compares against this one constant
# rather than scattering "en" string literals.
ENGLISH = "en"

_DETECT_SYSTEM_PROMPT = (
    "Identify the language of the user's message. Reply with ONLY the "
    "ISO 639-1 two-letter language code (e.g. en, es, fr, hi, de, pt, "
    "it, ar, zh). No other text, no punctuation, no explanation."
)


class TranslationError(Exception):
    """Raised when detection or translation cannot be completed.

    TRANSLATION_LAYER.md constraint 7: callers must treat this as a hard
    stop, never retried with a looser interpretation and never silently
    swallowed into a fabricated guess. See `messaging.py` for the two
    call sites and how each one responds to this exception.
    """


class TranslationClient:
    """Mirrors `WhatsAppCloudClient`/`AIGateway`'s provider-client shape.
    Reuses the platform's existing OpenAI credential (`settings.
    openai_api_key`) rather than introducing a second LLM credential —
    TRANSLATION_LAYER.md §7 left "which provider" open, and the existing
    AI Gateway is the only LLM already wired into this codebase."""

    name = "translation"

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and not settings.use_mock_ai

    @property
    def mode(self) -> str:
        return "live" if self.configured else "mock"

    def detect_language(self, text: str) -> str:
        """Returns an ISO 639-1 code (e.g. "en", "hi", "es").

        Mock mode always returns ENGLISH — deterministic for tests and
        local dev, and the same safe default the rest of this codebase
        uses elsewhere: an undetected language is treated as already-
        English (a no-op, TRANSLATION_LAYER.md §3) rather than guessed
        at. An empty message is never sent to a provider at all.
        """
        stripped = (text or "").strip()
        if not stripped or not self.configured:
            return ENGLISH
        try:
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _DETECT_SYSTEM_PROMPT},
                    {"role": "user", "content": stripped},
                ],
                temperature=0,
                max_tokens=5,
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            code = "".join(ch for ch in raw if ch.isalpha())[:2]
            return code or ENGLISH
        except Exception as exc:  # noqa: BLE001 — provider errors, network, parsing
            raise TranslationError(f"Language detection failed: {exc}") from exc

    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        """String -> String only, per this module's own docstring. Never
        inspects or returns anything beyond plain text — no confidence,
        no structured side channel, no opinion about intent
        (TRANSLATION_LAYER.md constraint 1).

        A no-op (returns `text` unchanged) whenever there is nothing to
        translate or source == target — the "English passes through as
        a no-op" rule in §3 applies to any same-language pair, not just
        English specifically.
        """
        stripped = text or ""
        if not stripped or source_language == target_language:
            return stripped
        if not self.configured:
            # Mock mode: deterministic passthrough. Never pretends to
            # have translated — same discipline as WhatsAppCloudClient's
            # mock `send()`, which logs instead of silently faking a
            # provider response.
            return stripped
        try:
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Translate the user's message from "
                            f"{source_language} to {target_language}. "
                            "Reply with ONLY the translated text — no "
                            "quotes, no explanation, no original text."
                        ),
                    },
                    {"role": "user", "content": stripped},
                ],
                temperature=0,
            )
            translated = (resp.choices[0].message.content or "").strip()
            if not translated:
                raise TranslationError("Translation provider returned empty text")
            return translated
        except TranslationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"Translation failed: {exc}") from exc


translation_client = TranslationClient()
