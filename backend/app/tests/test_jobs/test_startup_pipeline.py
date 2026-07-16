"""Tests for startup pipeline orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.startup_service import run_startup_pipeline


@pytest.mark.asyncio
async def test_startup_pipeline_disabled(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_PIPELINE_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    db = MagicMock()
    with patch("app.services.startup_service.deactivate_expired_alerts") as deactivate:
        await run_startup_pipeline(db)
    deactivate.assert_not_called()


@pytest.mark.asyncio
async def test_startup_pipeline_live_ingest(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("SHOWCASE_MODE", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    mock_run = MagicMock()
    mock_run.status = "success"
    mock_run.alerts_fetched = 5
    mock_run.alerts_created = 2
    mock_run.alerts_updated = 1
    mock_run.alerts_deactivated = 0
    mock_run.errors = []

    db = MagicMock()
    with (
        patch("app.services.startup_service.deactivate_expired_alerts", return_value=0),
        patch("app.services.startup_service.deactivate_fixture_alerts", return_value=0),
        patch(
            "app.services.startup_service._assets_table_empty",
            return_value=False,
        ),
        patch("app.services.startup_service.run_ingest", new=AsyncMock(return_value=mock_run)) as run_ingest,
    ):
        await run_startup_pipeline(db)

    run_ingest.assert_awaited_once()
    assert run_ingest.await_args.kwargs["generate_briefing"] is True


@pytest.mark.asyncio
async def test_startup_pipeline_imports_exposure_when_empty(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("SHOWCASE_MODE", "false")
    monkeypatch.setenv("EXPOSURE_AUTO_IMPORT", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    mock_run = MagicMock()
    mock_run.status = "success"
    mock_run.alerts_fetched = 0
    mock_run.alerts_created = 0
    mock_run.alerts_updated = 0
    mock_run.alerts_deactivated = 0
    mock_run.errors = []

    import_result = MagicMock()
    import_result.assets_created = 3
    import_result.assets_updated = 0
    import_result.total_assets = 3

    db = MagicMock()
    with (
        patch("app.services.startup_service.deactivate_expired_alerts", return_value=0),
        patch("app.services.startup_service.deactivate_fixture_alerts", return_value=0),
        patch("app.services.startup_service._assets_table_empty", return_value=True),
        patch(
            "app.services.startup_service.import_exposure_fixtures",
            return_value=import_result,
        ) as import_exposure,
        patch("app.services.startup_service.run_ingest", new=AsyncMock(return_value=mock_run)),
    ):
        await run_startup_pipeline(db)

    import_exposure.assert_called_once_with(db)


@pytest.mark.asyncio
async def test_startup_pipeline_skips_ingest_in_demo_mode(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SHOWCASE_MODE", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    db = MagicMock()
    with (
        patch("app.services.startup_service.deactivate_expired_alerts", return_value=0),
        patch("app.services.startup_service.run_ingest", new=AsyncMock()) as run_ingest,
    ):
        await run_startup_pipeline(db)

    run_ingest.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_pipeline_showcase_mode(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("SHOWCASE_MODE", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    db = MagicMock()
    with (
        patch("app.services.startup_service.deactivate_expired_alerts", return_value=0),
        patch("app.services.startup_service.deactivate_fixture_alerts", return_value=0),
        patch(
            "app.services.startup_service.ensure_showcase_data",
            new=AsyncMock(),
        ) as ensure_showcase,
        patch("app.services.startup_service.run_ingest", new=AsyncMock()) as run_ingest,
    ):
        await run_startup_pipeline(db)

    ensure_showcase.assert_awaited_once_with(db)
    run_ingest.assert_not_awaited()
