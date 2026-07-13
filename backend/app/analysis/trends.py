"""Trend analysis: compare current active counts vs 7-day rolling average."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.models.alert import Alert


@dataclass
class TrendAnomaly:
    dimension: str  # "category" | "country" | "global"
    key: str
    current_count: int
    rolling_avg: float
    ratio: float
    is_spike: bool


def _window_start(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)


def compute_rolling_averages(
    alerts: list[Alert],
    *,
    now: datetime | None = None,
    window_days: int | None = None,
) -> dict[str, dict[str, float]]:
    """Compute 7-day activity baseline per category and country.

    Uses count of alerts ingested within the window as proxy for the rolling
    average active count (no historical snapshots in MVP).
    """
    settings = get_settings()
    now = now or datetime.now(UTC)
    window = window_days or settings.risk_trend_window_days
    start = _window_start(now, window)

    by_category: dict[str, int] = defaultdict(int)
    by_country: dict[str, int] = defaultdict(int)
    global_in_window = 0

    for alert in alerts:
        ingested = alert.ingested_at
        if ingested.tzinfo is None:
            ingested = ingested.replace(tzinfo=UTC)
        if ingested >= start:
            global_in_window += 1
            by_category[alert.category] += 1
            if alert.country_code:
                by_country[alert.country_code] += 1

    return {
        "category": {k: float(v) for k, v in by_category.items()},
        "country": {k: float(v) for k, v in by_country.items()},
        "global": {"all": float(global_in_window)},
    }


def detect_trend_anomalies(
    alerts: list[Alert],
    *,
    now: datetime | None = None,
    spike_threshold: float = 1.5,
) -> list[TrendAnomaly]:
    """Flag unusual spikes where current active count > threshold × 7-day average."""
    settings = get_settings()
    now = now or datetime.now(UTC)
    rolling = compute_rolling_averages(alerts, now=now)

    active = [a for a in alerts if a.is_active]
    current_by_category: dict[str, int] = defaultdict(int)
    current_by_country: dict[str, int] = defaultdict(int)
    for alert in active:
        current_by_category[alert.category] += 1
        if alert.country_code:
            current_by_country[alert.country_code] += 1

    anomalies: list[TrendAnomaly] = []

    for key, current in current_by_category.items():
        avg = rolling["category"].get(key, 0.0)
        ratio = current / avg if avg > 0 else float(current)
        anomalies.append(
            TrendAnomaly(
                dimension="category",
                key=key,
                current_count=current,
                rolling_avg=round(avg, 2),
                ratio=round(ratio, 2),
                is_spike=ratio > spike_threshold and current >= 2,
            )
        )

    for key, current in current_by_country.items():
        avg = rolling["country"].get(key, 0.0)
        ratio = current / avg if avg > 0 else float(current)
        anomalies.append(
            TrendAnomaly(
                dimension="country",
                key=key,
                current_count=current,
                rolling_avg=round(avg, 2),
                ratio=round(ratio, 2),
                is_spike=ratio > spike_threshold and current >= 2,
            )
        )

    global_current = len(active)
    global_avg = rolling["global"]["all"]
    global_ratio = global_current / global_avg if global_avg > 0 else float(global_current)
    anomalies.append(
        TrendAnomaly(
            dimension="global",
            key="all",
            current_count=global_current,
            rolling_avg=round(global_avg, 2),
            ratio=round(global_ratio, 2),
            is_spike=global_ratio > spike_threshold and global_current >= 2,
        )
    )

    return sorted(
        [a for a in anomalies if a.is_spike],
        key=lambda a: -a.ratio,
    )


def global_rolling_avg(alerts: list[Alert], now: datetime | None = None) -> float:
    """Return global 7-day rolling average for trend modifier."""
    rolling = compute_rolling_averages(alerts, now=now)
    return rolling["global"]["all"]
