"""Background per-source ingest scheduler for container deployments."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.ingest_service import deactivate_expired_alerts, run_ingest
from app.services.retention_service import run_retention_cleanup

logger = get_logger(__name__)

_last_scheduler_run_at: datetime | None = None
_last_scheduler_error: str | None = None
_source_last_run_at: dict[str, datetime] = {}
_source_last_error: dict[str, str | None] = {}


def get_last_scheduler_run_at() -> datetime | None:
    return _last_scheduler_run_at


def get_last_scheduler_error() -> str | None:
    return _last_scheduler_error


def get_source_last_run_at(source_id: str) -> datetime | None:
    return _source_last_run_at.get(source_id)


def get_source_last_error(source_id: str) -> str | None:
    return _source_last_error.get(source_id)


def get_source_schedule_snapshot() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    snapshot: dict[str, dict[str, Any]] = {}
    for source_id in settings.get_scheduled_source_ids():
        snapshot[source_id] = {
            "interval_minutes": settings.get_source_interval_minutes(source_id),
            "last_run_at": (
                _source_last_run_at[source_id].isoformat()
                if source_id in _source_last_run_at
                else None
            ),
            "last_error": _source_last_error.get(source_id),
        }
    return snapshot


async def run_scheduled_ingest(sources: list[str] | None = None) -> None:
    """Run one ingest cycle (and optional briefing) in a fresh DB session."""
    global _last_scheduler_run_at, _last_scheduler_error

    settings = get_settings()
    db = SessionLocal()
    try:
        logger.info(
            "Scheduled ingest starting",
            extra={"demo_mode": settings.demo_mode, "sources": sources},
        )
        expired = deactivate_expired_alerts(db)
        if expired:
            logger.info("Pre-ingest: deactivated %d expired alerts", expired)
        run = await run_ingest(
            db,
            sources=sources,
            generate_briefing=settings.scheduler_generate_briefing if not sources else False,
        )
        db.commit()
        _last_scheduler_run_at = run.finished_at
        _last_scheduler_error = None
        if sources and len(sources) == 1:
            source_id = sources[0]
            _source_last_run_at[source_id] = run.finished_at
            _source_last_error[source_id] = None
        logger.info(
            "Scheduled ingest complete",
            extra={
                "status": run.status,
                "fetched": run.alerts_fetched,
                "alerts_created": run.alerts_created,
                "updated": run.alerts_updated,
                "deactivated": run.alerts_deactivated,
                "sources": sources,
            },
        )
        if run.errors:
            for err in run.errors:
                logger.error(
                    "Scheduled ingest source error",
                    extra={"source": err.get("source"), "status": "error"},
                )
                logger.error("Scheduled ingest source error: %s", err)
            if sources and len(sources) == 1:
                _source_last_error[sources[0]] = (
                    run.errors[0].get("error") if run.errors else "ingest failed"
                )
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
        if sources and len(sources) == 1:
            _source_last_error[sources[0]] = str(exc)
        logger.exception("Scheduled ingest failed")
    finally:
        db.close()


async def run_scheduled_retention_cleanup() -> None:
    settings = get_settings()
    if not settings.retention_cleanup_enabled:
        return

    db = SessionLocal()
    try:
        result = run_retention_cleanup(db)
        db.commit()
        if result["alerts_deleted"] or result["observed_events_deleted"]:
            logger.info("Scheduled retention cleanup: %s", result)
    except Exception:
        db.rollback()
        logger.exception("Scheduled retention cleanup failed")
    finally:
        db.close()


async def run_scheduled_briefing() -> None:
    settings = get_settings()
    if not settings.scheduler_generate_briefing:
        return

    db = SessionLocal()
    try:
        from app.services.briefing_service import generate_briefing

        generate_briefing(db, briefing_type="auto")
        db.commit()
        logger.info("Scheduled briefing generated")
    except Exception:
        db.rollback()
        logger.exception("Scheduled briefing generation failed")
    finally:
        db.close()


async def _source_scheduler_loop(source_id: str, stop_event: asyncio.Event) -> None:
    settings = get_settings()
    interval_seconds = settings.get_source_interval_minutes(source_id) * 60
    startup_delay = max(settings.scheduler_startup_delay_seconds, 0)

    logger.info(
        "Per-source scheduler started: source=%s interval=%d min startup_delay=%ds",
        source_id,
        settings.get_source_interval_minutes(source_id),
        startup_delay,
    )

    if startup_delay:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=startup_delay)
            return
        except TimeoutError:
            pass

    while not stop_event.is_set():
        await run_scheduled_ingest([source_id])
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            continue


async def _briefing_scheduler_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    interval_seconds = max(settings.ingest_interval_minutes, 1) * 60
    startup_delay = max(settings.scheduler_startup_delay_seconds, 0)

    logger.info(
        "Briefing scheduler enabled: interval=%d min startup_delay=%ds",
        settings.ingest_interval_minutes,
        startup_delay,
    )

    if startup_delay:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=startup_delay)
            return
        except TimeoutError:
            pass

    while not stop_event.is_set():
        await run_scheduled_briefing()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            continue


async def _retention_scheduler_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    if not settings.retention_cleanup_enabled:
        return

    await run_scheduled_retention_cleanup()
    interval_seconds = 24 * 60 * 60

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            await run_scheduled_retention_cleanup()


def start_scheduler() -> tuple[list[asyncio.Task[Any]], asyncio.Event | None]:
    """Start per-source background ingest loops when enabled in settings."""
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Ingest scheduler disabled (SCHEDULER_ENABLED=false)")
        return [], None

    source_ids = settings.get_scheduled_source_ids()
    if not source_ids:
        logger.info("Ingest scheduler enabled but no sources configured to schedule")
        return [], None

    stop_event = asyncio.Event()
    tasks: list[asyncio.Task[Any]] = []

    for source_id in source_ids:
        tasks.append(
            asyncio.create_task(
                _source_scheduler_loop(source_id, stop_event),
                name=f"ingest-scheduler-{source_id}",
            )
        )

    if settings.scheduler_generate_briefing:
        tasks.append(
            asyncio.create_task(
                _briefing_scheduler_loop(stop_event),
                name="briefing-scheduler",
            )
        )

    if settings.retention_cleanup_enabled:
        tasks.append(
            asyncio.create_task(
                _retention_scheduler_loop(stop_event),
                name="retention-scheduler",
            )
        )

    logger.info(
        "Per-source ingest scheduler enabled for %d sources: %s",
        len(source_ids),
        ", ".join(source_ids),
    )
    return tasks, stop_event


async def stop_scheduler(
    tasks: list[asyncio.Task[Any]] | None,
    stop_event: asyncio.Event | None,
) -> None:
    """Signal scheduler shutdown and wait for all loops to exit."""
    if not tasks or stop_event is None:
        return
    stop_event.set()
    for task in tasks:
        try:
            await asyncio.wait_for(task, timeout=120)
        except TimeoutError:
            logger.warning("Scheduler task %s did not stop within timeout; cancelling", task.get_name())
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
