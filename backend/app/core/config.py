"""Application configuration."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SOURCE_INTERVALS: dict[str, int] = {
    "nina": 15,
    "gdacs": 10,
    "noaa": 10,
    "usgs": 5,
    "eonet": 30,
    "noaa_swpc": 15,
    "firms": 60,
}

DEFAULT_ADMIN_TOKENS = frozenset({"dev-admin-token", "change-me-in-production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_format: str = "json"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/usefultool"
    demo_mode: bool = False
    showcase_mode: bool = False
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
    sources_live: str = "nina,gdacs,noaa"
    nina_user_agent: str = "GlobalRiskIntelligence/1.0 (contact@example.com)"
    nina_base_url: str = "https://warnung.bund.de/api31"
    nina_fetch_timeout_seconds: float = 10.0
    nina_max_response_bytes: int = 10 * 1024 * 1024
    nina_max_retries: int = 3
    nina_use_fixtures: bool = False
    nina_fallback_to_fixtures: bool = False
    gdacs_base_url: str = "https://www.gdacs.org"
    gdacs_fetch_timeout_seconds: float = 15.0
    gdacs_max_response_bytes: int = 10 * 1024 * 1024
    gdacs_max_retries: int = 3
    gdacs_use_fixtures: bool = False
    gdacs_fallback_to_fixtures: bool = True

    usgs_user_agent: str = "GlobalRiskIntelligence/1.0 (contact@example.com)"
    usgs_base_url: str = "https://earthquake.usgs.gov/earthquakes/feed/v1.0"
    usgs_fetch_timeout_seconds: float = 30.0
    usgs_max_response_bytes: int = 50 * 1024 * 1024
    usgs_max_retries: int = 3
    usgs_use_fixtures: bool = False
    usgs_fallback_to_fixtures: bool = True

    eonet_user_agent: str = "GlobalRiskIntelligence/1.0 (contact@example.com)"
    eonet_base_url: str = "https://eonet.gsfc.nasa.gov/api/v3"
    eonet_fetch_timeout_seconds: float = 30.0
    eonet_max_response_bytes: int = 50 * 1024 * 1024
    eonet_max_retries: int = 3
    eonet_use_fixtures: bool = False
    eonet_fallback_to_fixtures: bool = True

    noaa_swpc_user_agent: str = "GlobalRiskIntelligence/1.0 (contact@example.com)"
    noaa_swpc_base_url: str = "https://services.swpc.noaa.gov/products"
    noaa_swpc_fetch_timeout_seconds: float = 30.0
    noaa_swpc_max_response_bytes: int = 10 * 1024 * 1024
    noaa_swpc_max_retries: int = 3
    noaa_swpc_use_fixtures: bool = False
    noaa_swpc_fallback_to_fixtures: bool = True

    firms_user_agent: str = "GlobalRiskIntelligence/1.0 (contact@example.com)"
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov"
    firms_map_key: str = ""
    firms_product: str = "VIIRS_SNPP_NRT"
    firms_area_coords: str = "0,36,20,46"
    firms_day_range: int = 1
    firms_region_label: str = "Southern Europe / Mediterranean"
    firms_fetch_timeout_seconds: float = 30.0
    firms_max_response_bytes: int = 50 * 1024 * 1024
    firms_max_retries: int = 3
    firms_use_fixtures: bool = False
    firms_fallback_to_fixtures: bool = True
    firms_cluster_grid_deg: float = 0.5
    firms_cluster_time_hours: float = 24.0
    firms_min_cluster_points: int = 3

    llm_enabled: bool = False
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 30
    llm_max_tokens: int = 2048
    llm_max_events: int = 20
    llm_max_exposures_per_event: int = 10

    risk_score_scaling: int = 50
    risk_cluster_radius_km: int = 100
    risk_trend_window_days: int = 7

    auto_generate_briefing: bool = True

    startup_pipeline_enabled: bool = True
    exposure_auto_import: bool = False

    scheduler_enabled: bool = False
    ingest_interval_minutes: int = 15
    scheduler_generate_briefing: bool = True
    scheduler_startup_delay_seconds: int = 30
    source_schedules: str = ""
    nina_interval_minutes: int | None = None
    gdacs_interval_minutes: int | None = None
    noaa_interval_minutes: int | None = None
    usgs_interval_minutes: int | None = None
    eonet_interval_minutes: int | None = None
    noaa_swpc_interval_minutes: int | None = None
    firms_interval_minutes: int | None = None

    observed_events_retention_days: int = 90
    alerts_retention_days: int = 30
    retention_cleanup_enabled: bool = True

    correlation_time_window_hours: float = 24.0
    correlation_distance_km: float = 150.0
    correlation_auto_run: bool = True

    exposure_buffer_km: float = 50.0
    exposure_auto_run: bool = False

    implications_auto_run: bool = False

    def parsed_source_schedules(self) -> dict[str, int]:
        """Per-source ingest intervals from SOURCE_SCHEDULES JSON and *_INTERVAL_MINUTES env vars."""
        schedules: dict[str, int] = {}
        if self.source_schedules.strip():
            try:
                raw = json.loads(self.source_schedules)
            except json.JSONDecodeError:
                raw = {}
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(key, str) and isinstance(value, int | float):
                        schedules[key.strip().lower()] = max(int(value), 1)

        per_source = {
            "nina": self.nina_interval_minutes,
            "gdacs": self.gdacs_interval_minutes,
            "noaa": self.noaa_interval_minutes,
            "usgs": self.usgs_interval_minutes,
            "eonet": self.eonet_interval_minutes,
            "noaa_swpc": self.noaa_swpc_interval_minutes,
            "firms": self.firms_interval_minutes,
        }
        for source_id, minutes in per_source.items():
            if minutes is not None:
                schedules[source_id] = max(minutes, 1)
        return schedules

    def get_source_interval_minutes(self, source_id: str) -> int:
        schedules = self.parsed_source_schedules()
        if source_id in schedules:
            return schedules[source_id]
        if source_id in DEFAULT_SOURCE_INTERVALS:
            return DEFAULT_SOURCE_INTERVALS[source_id]
        return max(self.ingest_interval_minutes, 1)

    def get_scheduled_source_ids(self) -> list[str]:
        from app.sources.registry import _ADAPTERS

        if self.showcase_mode:
            return []
        if self.demo_mode:
            return list(_ADAPTERS.keys())
        live = [s.strip().lower() for s in self.sources_live.split(",") if s.strip()]
        return [source_id for source_id in live if source_id in _ADAPTERS]

    def is_weak_admin_token(self) -> bool:
        token = (self.admin_token or "").strip()
        return not token or token in DEFAULT_ADMIN_TOKENS or len(token) < 32


@lru_cache
def get_settings() -> Settings:
    return Settings()
