"""Background ingest scheduler for container deployments."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.ingest_service import deactivate_expired_alerts, run_ingest

logger = get_logger(__name__)

_last_scheduler_run_at: datetime | None = None
_last_scheduler_error: str | None = None


def get_last_scheduler_run_at() -> datetime | None:
    return _last_scheduler_run_at


def get_last_scheduler_error() -> str | None:
    return _last_scheduler_error


async def run_scheduled_ingest() -> None:
    """Run one ingest cycle (and optional briefing) in a fresh DB session."""
    global _last_scheduler_run_at, _last_scheduler_error

    settings = get_settings()
    db = SessionLocal()
    try:
        logger.info(
            "Scheduled ingest starting",
            extra={"demo_mode": settings.demo_mode},
        )
        expired = deactivate_expired_alerts(db)
        if expired:
            logger.info("Pre-ingest: deactivated %d expired alerts", expired)
        run = await run_ingest(
            db,
            generate_briefing=settings.scheduler_generate_briefing,
        )
        db.commit()
        _last_scheduler_run_at = run.finished_at
        _last_scheduler_error = None
        logger.info(
            "Scheduled ingest complete",
            extra={
                "status": run.status,
                "fetched": run.alerts_fetched,
                "created": run.alerts_created,
                "updated": run.alerts_updated,
                "deactivated": run.alerts_deactivated,
            },
        )
        if run.errors:
            for err in run.errors:
                logger.error(
                    "Scheduled ingest source error",
                    extra={"source": err.get("source"), "status": "error"},
                )
                logger.error("Scheduled ingest source error: %s", err)
        if run.status == "failed":
            _last_scheduler_error = (
                run.errors[0].get("error") if run.errors else "all sources failed"
            )
            logger.error(
                "Scheduled ingest failed",
                extra={"status": run.status, "source": run.source},
            )
    except Exception as exc:
        db.rollback()
        _last_scheduler_error = str(exc)
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
