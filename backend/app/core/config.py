from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_url import (
    database_backend,
    is_ephemeral_sqlite,
    normalize_database_url,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Revisit"
    app_version: str = "1.0.0-rc"
    environment: str = Field(default="development", description="development|staging|production|test")
    debug: bool = False
    public_base_url: str = "http://127.0.0.1:8000"
    frontend_base_url: str = "http://localhost:3000"
    argus_site_url: str = "https://argusai.online"
    argus_product_line: str = "Argus OS"

    # Production MUST use Postgres (Railway Postgres plugin). SQLite defaults are
    # for local/dev only — container SQLite is wiped on every Railway redeploy.
    database_url: str = "sqlite:///./revisit.db"
    # Escape hatch while attaching Postgres: ALLOW_EPHEMERAL_SQLITE=true
    allow_ephemeral_sqlite: bool = False
    # Set REQUIRE_DURABLE_STORAGE=true after Postgres is attached to refuse boot on SQLite
    require_durable_storage: bool = False
    # PILOT_READINESS.md §3 — escape hatch for a deliberate non-guest-
    # facing "production" deployment (e.g. internal staging under the
    # production DB). Same convention as ALLOW_EPHEMERAL_SQLITE: an
    # explicit, named opt-out, never a silent default.
    allow_mock_mode_in_production: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_secret: str = Field(
        default="dev-only-change-me-in-production-use-32chars+",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    use_mock_ai: bool = True
    # Prefer template + guest-memory agent ($0) for routine guest ops.
    # Set ZERO_COST_AGENT_ENABLED=false to always use the LLM gateway when live.
    zero_cost_agent_enabled: bool = True
    # Optional: use LLM for upsell choice only (still templates for welcome/review).
    llm_for_upsells: bool = False
    # Optional: use LLM for negative review drafts (default = template drafts).
    llm_for_review_replies: bool = False

    # Cloudbeds
    cloudbeds_client_id: str = ""
    cloudbeds_client_secret: str = ""
    cloudbeds_api_key: str = ""  # property API key alternative to OAuth
    cloudbeds_base_url: str = "https://api.cloudbeds.com/api/v1.2"
    cloudbeds_auth_url: str = "https://hotels.cloudbeds.com/api/v1.1"
    cloudbeds_property_id: str = ""
    cloudbeds_redirect_uri: str = "http://127.0.0.1:8000/api/webhooks/cloudbeds/oauth/callback"

    # WhatsApp (Meta Cloud API) — platform-level credentials only. There
    # is deliberately no global phone_number_id setting: which number a
    # message sends from is always resolved per-property
    # (Property.whatsapp_phone_number_id, CONCIERGE.md §3), never a
    # shared default, for both inbound and outbound.
    whatsapp_access_token: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: str = "revisit-whatsapp-verify"
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"

    # Email
    email_provider: str = "resend"  # resend | postmark | mock
    resend_api_key: str = ""
    resend_from_email: str = "onboarding@resend.dev"
    postmark_server_token: str = ""
    postmark_from_email: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_currency: str = "eur"

    # Google Business Profile / Reviews (official)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_account_id: str = ""
    google_location_id: str = ""

    rate_limit_per_minute: int = 120
    csv_max_bytes: int = 1_000_000
    csv_max_rows: int = 500
    pdf_max_bytes: int = 8_000_000
    pdf_max_pages: int = 40
    pdf_max_reservations_per_file: int = 25
    # Internal extraction-confidence gate (never surfaced to a hotel — see
    # PDF_IMPORT.md §4). Below this, a row is "Needs Review" regardless of
    # whether every field happened to parse.
    pdf_confidence_threshold: float = 0.75
    # A menu PDF legitimately has far more line items than a booking
    # confirmation has reservations — its own cap, not a reuse of
    # pdf_max_reservations_per_file.
    menu_max_items_per_file: int = 200
    seed_on_startup: bool = True
    auto_create_tables: bool = True

    # Platform owner (main admin account for the demo hotel workspace)
    # Empty OWNER_EMAIL in env must not wipe the default — seed and admin
    # gate both depend on a real address.
    owner_email: str = "dkhadikar@gmail.com"
    owner_name: str = "Deepanshu"
    owner_password: str = Field(
        default="",
        description="Password for owner_email. Set OWNER_PASSWORD in production.",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_db_url(cls, v: object) -> str:
        return normalize_database_url(str(v) if v is not None else "")

    @field_validator("owner_email", mode="before")
    @classmethod
    def normalize_owner_email(cls, v: object) -> str:
        raw = (str(v).strip().lower() if v is not None else "")
        return raw or "dkhadikar@gmail.com"

    @field_validator("owner_name", mode="before")
    @classmethod
    def normalize_owner_name(cls, v: object) -> str:
        raw = (str(v).strip() if v is not None else "")
        return raw or "Deepanshu"

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def reject_ephemeral_sqlite_in_production(self) -> "Settings":
        if (
            self.environment == "production"
            and is_ephemeral_sqlite(self.database_url)
            and self.require_durable_storage
            and not self.allow_ephemeral_sqlite
        ):
            raise ValueError(
                "Production cannot use container SQLite — data (passwords, trials, "
                "hotels) is wiped on every Railway redeploy. Add Railway Postgres, "
                "set DATABASE_URL to the Postgres URL, and redeploy. Temporary "
                "escape hatch: ALLOW_EPHEMERAL_SQLITE=true (data will still be lost)."
            )
        return self

    @model_validator(mode="after")
    def reject_mock_mode_in_production(self) -> "Settings":
        """PILOT_READINESS.md §3 — mock mode must be impossible to
        mistake for production readiness. A pilot/production deployment
        silently running with AI/translation and WhatsApp still in mock
        mode produces identical-looking success logs to a correctly
        configured one: a non-English guest gets their own message
        echoed back untranslated, and no WhatsApp send ever reaches a
        real phone. This turns that into a loud startup failure instead
        of a silent failure discovered only when a real guest messages
        in. Deliberately does not check `whatsapp_app_secret` — its own
        absence already fails closed today (`verify_signature` rejects
        unsigned webhooks in production), a loud failure already, not a
        silent one, so it isn't part of this specific guard.
        """
        if self.environment == "production" and not self.allow_mock_mode_in_production:
            problems = []
            if self.use_mock_ai:
                problems.append("USE_MOCK_AI=true")
            if not self.openai_api_key:
                problems.append("OPENAI_API_KEY is not set")
            if not self.whatsapp_access_token:
                problems.append("WHATSAPP_ACCESS_TOKEN is not set")
            if problems:
                raise ValueError(
                    "Refusing to start in production with mock mode still "
                    "active (" + "; ".join(problems) + "). Set real "
                    "credentials, or set ALLOW_MOCK_MODE_IN_PRODUCTION=true "
                    "for a deliberate non-guest-facing production "
                    "deployment. (PILOT_READINESS.md §3)"
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_backend(self) -> str:
        return database_backend(self.database_url)

    @property
    def storage_durable(self) -> bool:
        """False when using container-local SQLite (ephemeral on Railway)."""
        return not is_ephemeral_sqlite(self.database_url)

    @property
    def cloudbeds_configured(self) -> bool:
        return bool(self.cloudbeds_api_key or (self.cloudbeds_client_id and self.cloudbeds_client_secret))

    @property
    def whatsapp_configured(self) -> bool:
        # Platform-level only — whether a *specific* tenant can send is a
        # separate, per-property check (Property.whatsapp_phone_number_id).
        return bool(self.whatsapp_access_token)

    @property
    def email_configured(self) -> bool:
        if self.email_provider == "resend":
            return bool(self.resend_api_key)
        if self.email_provider == "postmark":
            return bool(self.postmark_server_token)
        return False

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def stripe_configured(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def google_reviews_configured(self) -> bool:
        return bool(self.google_refresh_token and self.google_location_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
