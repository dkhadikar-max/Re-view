from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Guest Revenue Agent"
    app_version: str = "0.1.0"
    debug: bool = True
    database_url: str = "sqlite:///./gra.db"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    openai_api_key: str = ""
    use_mock_ai: bool = True
    default_tenant_id: str = "demo-hotel"

    class Config:
        env_file = ".env"


settings = Settings()
