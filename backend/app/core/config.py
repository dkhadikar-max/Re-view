from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Revisit"
    app_version: str = "1.0.0-rc"
    environment: str = Field(default="development", description="development|staging|production|test")
    debug: bool = False
    public_base_url: str = "http://127.0.0.1:8000"
    frontend_base_url: str = "http://localhost:3000"
    argus_site_url: str = "https://argusos-psi.vercel.app"
    argus_product_line: str = "Argus OS"

    database_url: str = "sqlite:///./revisit.db"
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

    # Cloudbeds
    cloudbeds_client_id: str = ""
    cloudbeds_client_secret: str = ""
    cloudbeds_api_key: str = ""  # property API key alternative to OAuth
    cloudbeds_base_url: str = "https://api.cloudbeds.com/api/v1.2"
    cloudbeds_auth_url: str = "https://hotels.cloudbeds.com/api/v1.1"
    cloudbeds_property_id: str = ""
    cloudbeds_redirect_uri: str = "http://127.0.0.1:8000/api/webhooks/cloudbeds/oauth/callback"

    # WhatsApp (Meta Cloud API)
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
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
    seed_on_startup: bool = True
    auto_create_tables: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cloudbeds_configured(self) -> bool:
        return bool(self.cloudbeds_api_key or (self.cloudbeds_client_id and self.cloudbeds_client_secret))

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id)

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

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
