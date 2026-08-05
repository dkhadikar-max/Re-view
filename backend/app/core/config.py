from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Guest Revenue Agent"
    app_version: str = "0.2.0"
    environment: str = Field(default="development", description="development|staging|production")
    debug: bool = False

    database_url: str = "sqlite:///./gra.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_secret: str = Field(
        default="dev-only-change-me-in-production-use-32chars+",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    openai_api_key: str = ""
    use_mock_ai: bool = True

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
