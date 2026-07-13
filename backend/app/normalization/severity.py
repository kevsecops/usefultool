"""Severity normalization."""

from app.schemas.common import Severity

_CAP_SEVERITY_MAP: dict[str, Severity] = {
    "unknown": Severity.UNKNOWN,
    "minor": Severity.MINOR,
    "moderate": Severity.MODERATE,
    "severe": Severity.SEVERE,
    "extreme": Severity.EXTREME,
}

_GDACS_ALERT_LEVEL_MAP: dict[str, Severity] = {
    "green": Severity.MINOR,
    "orange": Severity.MODERATE,
    "red": Severity.SEVERE,
}


def normalize_cap_severity(value: str | None) -> Severity:
    if not value:
        return Severity.UNKNOWN
    return _CAP_SEVERITY_MAP.get(value.strip().lower(), Severity.UNKNOWN)


def normalize_gdacs_alert_level(value: str | None, alert_score: float | None = None) -> Severity:
    if not value:
        return Severity.UNKNOWN
    base = _GDACS_ALERT_LEVEL_MAP.get(value.strip().lower(), Severity.UNKNOWN)
    if value.strip().lower() == "orange" and alert_score and alert_score >= 2:
        return Severity.SEVERE
    if value.strip().lower() == "red" and alert_score and alert_score >= 3:
        return Severity.EXTREME
    return base
