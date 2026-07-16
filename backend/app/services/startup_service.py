"""Configurable data pipeline orchestration on backend container start."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.exposure_asset import ExposureAsset
from app.services.alert_fixture import deactivate_fixture_alerts
from app.services.exposure_service import import_exposure_fixtures
from app.services.ingest_service import deactivate_expired_alerts, run_ingest
from app.services.showcase_service import ensure_showcase_data

logger = get_logger(__name__)


def _assets_table_empty(db: Session) -> bool:
    count = db.scalar(select(func.count()).select_from(ExposureAsset))
    return (count or 0) == 0


def _should_import_exposure(db: Session) -> bool:
    settings = get_settings()
    if settings.showcase_mode:
        return False
    return settings.exposure_auto_import or _assets_table_empty(db)


async def run_startup_pipeline(db: Session) -> None:
    """Run the configured ingest/analysis pipeline once at container start."""
    settings = get_settings()
    if not settings.startup_pipeline_enabled:
        logger.info("Startup pipeline disabled (STARTUP_PIPELINE_ENABLED=false)")
        return

    expired = deactivate_expired_alerts(db)
    if expired:
        logger.info("Startup: deactivated %d expired alerts", expired)

    if not settings.demo_mode:
        fixture_count = deactivate_fixture_alerts(db)
        if fixture_count:
            logger.info(
                "Startup: deactivated %d fixture-origin alerts (demo_mode=false)",
                fixture_count,
            )

    if _should_import_exposure(db):
        try:
            result = import_exposure_fixtures(db)
            logger.info(
                "Startup: exposure fixtures imported (created=%d updated=%d total=%d)",
                result.assets_created,
                result.assets_updated,
                result.total_assets,
            )
        except Exception:
            logger.exception("Startup exposure import failed")

    if settings.showcase_mode:
        await ensure_showcase_data(db)
        return

    if settings.demo_mode:
        logger.info(
            "Startup: skipping ingest (DEMO_MODE=true); run `python -m app.jobs.cli ingest` manually"
        )
        return

    logger.info(
        "Startup: running live ingest (sources=%s, correlation=%s, exposure=%s, implications=%s, briefing=%s)",
        settings.sources_live,
        settings.correlation_auto_run,
        settings.exposure_auto_run,
        settings.implications_auto_run,
        settings.auto_generate_briefing,
    )
    run = await run_ingest(db, generate_briefing=settings.auto_generate_briefing)
    logger.info(
        "Startup ingest complete: status=%s fetched=%d created=%d updated=%d deactivated=%d",
        run.status,
        run.alerts_fetched,
        run.alerts_created,
        run.alerts_updated,
        run.alerts_deactivated,
    )
    if run.errors:
        for err in run.errors:
            logger.error("Startup ingest source error: %s", err)
