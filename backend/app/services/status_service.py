"""Platform status for health and admin endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.jobs import scheduler as scheduler_module
from app.models.alert import Alert
from app.models.ingest_run import IngestRun
from app.normalization.datetime_utils import utc_now
from app.services.alert_active import filter_effectively_active
from app.services.alert_fixture import extract_ingest_mode, is_fixture_alert
from app.sources.registry import get_adapters


def _latest_ingest_run(db: Session) -> IngestRun | None:
    return db.scalar(select(IngestRun).order_by(desc(IngestRun.finished_at)).limit(1))


def _active_alerts(db: Session) -> list[Alert]:
    now = utc_now()
    db_alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    return filter_effectively_active(db_alerts, now=now)


def _public_active_alerts(db: Session) -> list[Alert]:
    """Effective-active alerts visible in public API (excludes fixtures when not demo)."""
    alerts = _active_alerts(db)
    if get_settings().demo_mode:
        return alerts
    return [alert for alert in alerts if not is_fixture_alert(alert)]


def _alert_counts_by_source(alerts: list[Alert]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for alert in alerts:
        counts[alert.source] = counts.get(alert.source, 0) + 1
    return counts


def _scheduler_next_run_estimate(last_ingest_at: datetime | None) -> datetime | None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        return None
    base = last_ingest_at or scheduler_module.get_last_scheduler_run_at()
    if base is None:
        return utc_now() + timedelta(seconds=max(settings.scheduler_startup_delay_seconds, 0))
    return base + timedelta(minutes=max(settings.ingest_interval_minutes, 1))


def _overall_status(*, db_connected: bool, last_ingest_status: str | None) -> str:
    if not db_connected:
        return "degraded"
    if last_ingest_status == "failed":
        return "degraded"
    if scheduler_module.get_last_scheduler_error():
        return "degraded"
    return "ok"


def get_health_status(db: Session) -> dict:
    """Summary status for GET /health."""
    settings = get_settings()
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    last_run = _latest_ingest_run(db)
    public_alerts = _public_active_alerts(db)
    alert_counts = _alert_counts_by_source(public_alerts)

    last_ingest_at = last_run.finished_at if last_run else None
    last_ingest_status = last_run.status if last_run else None
    last_ingest_errors = last_run.errors or [] if last_run else []
    last_ingest_error = None
    if last_ingest_status == "failed" and last_ingest_errors:
        last_ingest_error = last_ingest_errors[0].get("error")
    elif scheduler_module.get_last_scheduler_error():
        last_ingest_error = scheduler_module.get_last_scheduler_error()

    return {
        "status": _overall_status(
            db_connected=db_status == "connected",
            last_ingest_status=last_ingest_status,
        ),
        "version": settings.app_version,
        "db": db_status,
        "demo_mode": settings.demo_mode,
        "scheduler": {
            "enabled": settings.scheduler_enabled,
            "interval_minutes": settings.ingest_interval_minutes,
            "last_run_at": (
                last_ingest_at.isoformat()
                if last_ingest_at
                else (
                    scheduler_module.get_last_scheduler_run_at().isoformat()
                    if scheduler_module.get_last_scheduler_run_at()
                    else None
                )
            ),
            "last_error": scheduler_module.get_last_scheduler_error(),
        },
        "last_ingest_at": last_ingest_at.isoformat() if last_ingest_at else None,
        "last_ingest_status": last_ingest_status,
        "last_ingest_error": last_ingest_error,
        "alert_counts": alert_counts,
        "active_alert_count": len(public_alerts),
    }


async def get_admin_status(db: Session) -> dict:
    """Detailed status for GET /api/v1/admin/status."""
    settings = get_settings()
    last_run = _latest_ingest_run(db)
    public_alerts = _public_active_alerts(db)
    all_active = _active_alerts(db)
    fixture_count = sum(1 for alert in all_active if is_fixture_alert(alert))

    recent_runs = db.scalars(
        select(IngestRun).order_by(desc(IngestRun.started_at)).limit(10)
    ).all()

    sources_status = []
    for adapter in get_adapters():
        health = await adapter.health_check()
        sources_status.append(
            {
                "id": adapter.source_id,
                "healthy": health.is_healthy,
                "last_fetch": (
                    health.last_success_at.isoformat() if health.last_success_at else None
                ),
                "ingest_mode": health.ingest_mode,
                "alerts_fetched": health.alerts_fetched,
                "error_message": health.error_message,
            }
        )

    last_ingest_at = last_run.finished_at if last_run else None
    return {
        "demo_mode": settings.demo_mode,
        "scheduler": {
            "enabled": settings.scheduler_enabled,
            "interval_minutes": settings.ingest_interval_minutes,
            "generate_briefing": settings.scheduler_generate_briefing,
            "startup_delay_seconds": settings.scheduler_startup_delay_seconds,
            "last_run_at": (
                scheduler_module.get_last_scheduler_run_at().isoformat()
                if scheduler_module.get_last_scheduler_run_at()
                else (last_ingest_at.isoformat() if last_ingest_at else None)
            ),
            "next_run_estimate": (
                _scheduler_next_run_estimate(last_ingest_at).isoformat()
                if settings.scheduler_enabled
                else None
            ),
            "last_error": scheduler_module.get_last_scheduler_error(),
        },
        "last_ingest_at": last_ingest_at.isoformat() if last_ingest_at else None,
        "last_ingest_status": last_run.status if last_run else None,
        "last_ingest_errors": last_run.errors or [] if last_run else [],
        "metrics": {
            "active_alert_count": len(public_alerts),
            "fixture_alert_count": fixture_count,
            "alert_counts_by_source": _alert_counts_by_source(public_alerts),
            "total_alerts_in_db": db.scalar(select(func.count()).select_from(Alert)) or 0,
        },
        "recent_ingest_runs": [
            {
                "id": str(run.id),
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "source": run.source,
                "status": run.status,
                "alerts_fetched": run.alerts_fetched,
                "alerts_created": run.alerts_created,
                "alerts_updated": run.alerts_updated,
                "alerts_deactivated": run.alerts_deactivated,
                "errors": run.errors or [],
            }
            for run in recent_runs
        ],
        "sources": sources_status,
    }
