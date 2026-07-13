"""Background ingest scheduler for container deployments."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.briefing_service import generate_briefing
from app.services.ingest_service import run_ingest

logger = get_logger(__name__)


async def run_scheduled_ingest() -> None:
    """Run one ingest cycle (and optional briefing) in a fresh DB session."""
    settings = get_settings()
    db = SessionLocal()
    try:
        run = await run_ingest(
            db,
            generate_briefing=settings.scheduler_generate_briefing,
        )
        db.commit()
        logger.info(
            "Scheduled ingest complete: status=%s fetched=%d created=%d updated=%d deactivated=%d",
            run.status,
            run.alerts_fetched,
            run.alerts_created,
            run.alerts_updated,
            run.alerts_deactivated,
        )
        if run.errors:
            for err in run.errors:
                logger.warning("Scheduled ingest source error: %s", err)
    except Exception:
        db.rollback()
        logger.exception("Scheduled ingest failed")
    finally:
        db.close()


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    interval_seconds = max(settings.ingest_interval_minutes, 1) * 60
    startup_delay = max(settings.scheduler_startup_delay_seconds, 0)

    logger.info(
        "Ingest scheduler enabled: interval=%d min, generate_briefing=%s, startup_delay=%ds",
        settings.ingest_interval_minutes,
        settings.scheduler_generate_briefing,
        startup_delay,
    )

    if startup_delay:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=startup_delay)
            return
        except TimeoutError:
            pass

    while not stop_event.is_set():
        await run_scheduled_ingest()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            continue


def start_scheduler() -> tuple[asyncio.Task[Any] | None, asyncio.Event | None]:
    """Start background ingest loop when enabled in settings."""
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Ingest scheduler disabled (SCHEDULER_ENABLED=false)")
        return None, None

    stop_event = asyncio.Event()
    task = asyncio.create_task(_scheduler_loop(stop_event), name="ingest-scheduler")
    return task, stop_event


async def stop_scheduler(
    task: asyncio.Task[Any] | None,
    stop_event: asyncio.Event | None,
) -> None:
    """Signal scheduler shutdown and wait for the loop to exit."""
    if task is None or stop_event is None:
        return
    stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=120)
    except TimeoutError:
        logger.warning("Ingest scheduler did not stop within timeout; cancelling task")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
