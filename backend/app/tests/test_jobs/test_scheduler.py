"""Tests for background ingest scheduler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import DEFAULT_SOURCE_INTERVALS, get_settings
from app.jobs.scheduler import (
    get_source_schedule_snapshot,
    run_scheduled_ingest,
    start_scheduler,
)


@pytest.mark.asyncio
async def test_run_scheduled_ingest_commits_on_success() -> None:
    mock_run = AsyncMock()
    mock_run.status = "success"
    mock_run.alerts_fetched = 10
    mock_run.alerts_created = 2
    mock_run.alerts_updated = 1
    mock_run.alerts_deactivated = 0
    mock_run.errors = []
    mock_run.finished_at = mock_run.started_at = None

    with (
        patch("app.jobs.scheduler.SessionLocal") as session_local,
        patch("app.jobs.scheduler.run_ingest", new=AsyncMock(return_value=mock_run)) as run_ingest,
        patch("app.jobs.scheduler.deactivate_expired_alerts", return_value=0),
    ):
        db = session_local.return_value
        await run_scheduled_ingest(["noaa"])

    run_ingest.assert_awaited_once()
    assert run_ingest.await_args.kwargs["generate_briefing"] is False
    db.commit.assert_called_once()
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.scheduler_enabled is False
    assert settings.ingest_interval_minutes == 15
    assert settings.auto_generate_briefing is True
    assert settings.scheduler_generate_briefing is True
    assert settings.scheduler_startup_delay_seconds == 30


def test_scheduler_enabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.scheduler_enabled is True


def test_per_source_interval_from_env_var(monkeypatch) -> None:
    monkeypatch.setenv("USGS_INTERVAL_MINUTES", "7")
    monkeypatch.setenv("NOAA_INTERVAL_MINUTES", "12")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.get_source_interval_minutes("usgs") == 7
    assert settings.get_source_interval_minutes("noaa") == 12
    assert settings.get_source_interval_minutes("nina") == DEFAULT_SOURCE_INTERVALS["nina"]


def test_per_source_interval_from_json(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_SCHEDULES", '{"gdacs": 8, "firms": 45}')
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.get_source_interval_minutes("gdacs") == 8
    assert settings.get_source_interval_minutes("firms") == 45


def test_env_var_overrides_json_schedule(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_SCHEDULES", '{"gdacs": 8}')
    monkeypatch.setenv("GDACS_INTERVAL_MINUTES", "11")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.get_source_interval_minutes("gdacs") == 11


def test_scheduled_sources_follow_sources_live(monkeypatch) -> None:
    monkeypatch.setenv("SOURCES_LIVE", "nina,noaa,usgs")
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.get_scheduled_source_ids() == ["nina", "noaa", "usgs"]


def test_scheduled_sources_all_in_demo_mode(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert "nina" in settings.get_scheduled_source_ids()
    assert "firms" in settings.get_scheduled_source_ids()


def test_start_scheduler_creates_per_source_tasks(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("SOURCES_LIVE", "noaa,usgs")
    monkeypatch.setenv("SCHEDULER_GENERATE_BRIEFING", "false")
    get_settings.cache_clear()

    with patch("app.jobs.scheduler.asyncio.create_task") as create_task:
        def _fake_task(coro, **kwargs):
            task = MagicMock()
            task.get_name.return_value = kwargs.get("name", "")
            return task

        create_task.side_effect = _fake_task
        tasks, stop_event = start_scheduler()

    assert stop_event is not None
    assert len(tasks) >= 2
    names = {task.get_name() for task in tasks if hasattr(task, "get_name")}
    assert "ingest-scheduler-noaa" in names
    assert "ingest-scheduler-usgs" in names


def test_source_schedule_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("SOURCES_LIVE", "usgs")
    monkeypatch.setenv("USGS_INTERVAL_MINUTES", "4")
    get_settings.cache_clear()
    snapshot = get_source_schedule_snapshot()
    assert snapshot["usgs"]["interval_minutes"] == 4
