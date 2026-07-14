"""Fixture alert detection, filtering, and cleanup."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.alert import Alert


def is_fixture_alert(alert: Alert) -> bool:
    """True when alert originated from demo fixtures (not showcase)."""
    if alert.source_alert_id and "DEMO" in alert.source_alert_id.upper():
        return True
    raw = alert.raw_payload or {}
    mode = raw.get("_ingest_mode") or raw.get("ingest_mode")
    return mode == "fixture"


def is_showcase_alert(alert: Alert) -> bool:
    """True when alert originated from SHOWCASE_MODE curated fixtures."""
    raw = alert.raw_payload or {}
    mode = raw.get("_ingest_mode") or raw.get("ingest_mode")
    return mode == "showcase"


def extract_ingest_mode(alert: Alert) -> str:
    """Derive ingest mode label for API responses."""
    raw = alert.raw_payload or {}
    mode = raw.get("_ingest_mode") or raw.get("ingest_mode")
    if mode in ("fixture", "live", "showcase"):
        return mode
    if is_fixture_alert(alert):
        return "fixture"
    return "live"


def fixture_alert_filter():
    """SQLAlchemy expression matching fixture-origin alerts."""
    return or_(
        Alert.source_alert_id.ilike("%DEMO%"),
        and_(
            Alert.raw_payload["_ingest_mode"].astext.isnot(None),
            Alert.raw_payload["_ingest_mode"].astext == "fixture",
        ),
        and_(
            Alert.raw_payload["ingest_mode"].astext.isnot(None),
            Alert.raw_payload["ingest_mode"].astext == "fixture",
        ),
    )


def deactivate_fixture_alerts(db: Session) -> int:
    """Deactivate all fixture-origin alerts. Used when DEMO_MODE=false."""
    active_alerts = db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()
    deactivated = 0
    for alert in active_alerts:
        if is_fixture_alert(alert):
            alert.is_active = False
            deactivated += 1
    return deactivated
