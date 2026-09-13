"""Typed application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Values are read from environment variables (and an optional ``.env`` file).
    See ``.env.example`` for the documented set of variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "GitHub Intelligence Backend"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Database (PostgreSQL)
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/github_intelligence"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # GitHub integration placeholders. These hold configuration only; no real
    # values are committed and the auth model is not yet decided.
    github_api_url: str = "https://api.github.com"
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_webhook_secret: str | None = None
    github_app_id: str | None = None
    github_app_private_key: str | None = None

    # Supabase Auth (third-party identity provider). No secrets are committed;
    # set these via environment variables.
    supabase_jwks_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"

    @property
    def is_production(self) -> bool:
        """Whether the application is running in a production environment."""
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
