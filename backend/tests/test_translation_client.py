"""TranslationClient — TRANSLATION_LAYER.md.

Unit tests of the provider client itself, independent of messaging.py's
wiring. `use_mock_ai=True` is this repo's test-environment default
(app/core/config.py), so `configured` is always False here — no network
access or API key required, matching every other provider client test
in this suite (`WhatsAppCloudClient`, `AIGateway`).
"""

from __future__ import annotations

from app.integrations.translation import ENGLISH, TranslationClient


def test_mock_mode_when_unconfigured():
    client = TranslationClient()
    assert client.configured is False
    assert client.mode == "mock"


def test_detect_language_mock_mode_always_returns_english():
    """Mock mode's deterministic default: an undetected language is
    treated as already-English (TRANSLATION_LAYER.md §3's no-op rule)
    rather than guessed at — never a random/varying result in tests."""
    client = TranslationClient()
    assert client.detect_language("Hola, ¿cómo estás?") == ENGLISH
    assert client.detect_language("") == ENGLISH
    assert client.detect_language("   ") == ENGLISH


def test_translate_mock_mode_is_passthrough():
    """Mock mode never pretends to have translated — same discipline as
    WhatsAppCloudClient's mock send()."""
    client = TranslationClient()
    assert client.translate("Hello", source_language="en", target_language="es") == "Hello"


def test_translate_same_language_is_noop_without_calling_provider(monkeypatch):
    """Same source/target must short-circuit before any provider call —
    proven by the fact this succeeds even when `configured` is forced
    True with no real API key backing it."""
    client = TranslationClient()
    monkeypatch.setattr(TranslationClient, "configured", property(lambda self: True))
    assert client.translate("Hello", source_language="en", target_language="en") == "Hello"


def test_translate_empty_text_is_noop():
    client = TranslationClient()
    assert client.translate("", source_language="es", target_language="en") == ""
