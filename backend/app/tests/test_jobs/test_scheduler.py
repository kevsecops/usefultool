"""Tests for background ingest scheduler."""

from unittest.mock import AsyncMock, patch

import pytest

from app.jobs.scheduler import run_scheduled_ingest


@pytest.mark.asyncio
async def test_run_scheduled_ingest_commits_on_success() -> None:
    mock_run = AsyncMock()
    mock_run.status = "success"
    mock_run.alerts_fetched = 10
    mock_run.alerts_created = 2
    mock_run.alerts_updated = 1
    mock_run.alerts_deactivated = 0
    mock_run.errors = []

    with (
        patch("app.jobs.scheduler.SessionLocal") as session_local,
        patch("app.jobs.scheduler.run_ingest", new=AsyncMock(return_value=mock_run)) as run_ingest,
    ):
        db = session_local.return_value
        await run_scheduled_ingest()

    run_ingest.assert_awaited_once()
    db.commit.assert_called_once()
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.scheduler_enabled is False
    assert settings.ingest_interval_minutes == 15
