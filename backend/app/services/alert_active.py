"""Helpers for determining whether an alert is effectively active."""

from datetime import datetime

from app.models.alert import Alert
from app.normalization.datetime_utils import utc_now


def is_expired(alert: Alert, now: datetime | None = None) -> bool:
    """True when the alert has an expires_at in the past."""
    if alert.expires_at is None:
        return False
    now = now or utc_now()
    return alert.expires_at < now


def is_effectively_active(alert: Alert, now: datetime | None = None) -> bool:
    """True when is_active and not past expires_at."""
    if not alert.is_active:
        return False
    return not is_expired(alert, now)


def filter_effectively_active(alerts: list[Alert], now: datetime | None = None) -> list[Alert]:
    now = now or utc_now()
    return [alert for alert in alerts if is_effectively_active(alert, now)]
