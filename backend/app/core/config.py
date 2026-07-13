"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.1.0"
    log_level: str = "INFO"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/usefultool"
    demo_mode: bool = False
    fixtures_dir: Path = Path("fixtures")
    admin_token: str = "dev-admin-token"
    frontend_url: str = "http://localhost:3000"

    noaa_user_agent: str = "GlobalRiskIntelligence/1.0 (contact@example.com)"
    noaa_base_url: str = "https://api.weather.gov"
    noaa_fetch_timeout_seconds: float = 30.0
    noaa_max_response_bytes: int = 50 * 1024 * 1024
    noaa_max_retries: int = 3
    noaa_use_fixtures: bool = False
    noaa_fallback_to_fixtures: bool = True
    sources_live: str = "noaa"
    nina_base_url: str = "https://warnung.bund.de/api31"
    gdacs_base_url: str = "https://www.gdacs.org"

    llm_enabled: bool = True
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 30
    llm_max_tokens: int = 2048

    risk_score_scaling: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()
