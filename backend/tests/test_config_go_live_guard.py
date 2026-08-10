"""Production mock-mode guard — PILOT_READINESS.md §3.

Mock mode must be impossible to mistake for production readiness: a
pilot/production deployment silently running with AI/translation or
WhatsApp still in mock mode looks identical (in logs) to a correctly
configured one, but no guest ever actually receives a reply. This
guard fails loudly at Settings construction time instead.

Each test constructs `Settings` directly with every guard-relevant
field passed explicitly, so a developer's local `.env` file (if any)
can never leak into these assertions.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        environment="production",
        use_mock_ai=False,
        openai_api_key="sk-real-key",
        whatsapp_access_token="real-token",
        allow_mock_mode_in_production=False,
        jwt_secret="a" * 32,
    )
    base.update(overrides)
    return Settings(**base)


def test_production_with_mock_ai_true_is_rejected():
    with pytest.raises(ValidationError, match="USE_MOCK_AI=true"):
        _settings(use_mock_ai=True)


def test_production_with_missing_openai_key_is_rejected():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is not set"):
        _settings(openai_api_key="")


def test_production_with_missing_whatsapp_token_is_rejected():
    with pytest.raises(ValidationError, match="WHATSAPP_ACCESS_TOKEN is not set"):
        _settings(whatsapp_access_token="")


def test_production_with_multiple_problems_lists_all_of_them():
    with pytest.raises(ValidationError) as exc_info:
        _settings(use_mock_ai=True, openai_api_key="", whatsapp_access_token="")
    message = str(exc_info.value)
    assert "USE_MOCK_AI=true" in message
    assert "OPENAI_API_KEY is not set" in message
    assert "WHATSAPP_ACCESS_TOKEN is not set" in message


def test_production_with_everything_configured_does_not_raise():
    settings = _settings()
    assert settings.environment == "production"


def test_escape_hatch_allows_a_deliberate_mock_production_deployment():
    settings = _settings(
        use_mock_ai=True,
        openai_api_key="",
        whatsapp_access_token="",
        allow_mock_mode_in_production=True,
    )
    assert settings.allow_mock_mode_in_production is True


@pytest.mark.parametrize("environment", ["development", "staging", "test"])
def test_non_production_environments_are_never_blocked(environment):
    """The guard is specific to production — a developer's laptop or a
    staging deployment is allowed to run in mock mode freely."""
    settings = Settings(
        environment=environment,
        use_mock_ai=True,
        openai_api_key="",
        whatsapp_access_token="",
        jwt_secret="a" * 32,
    )
    assert settings.environment == environment
