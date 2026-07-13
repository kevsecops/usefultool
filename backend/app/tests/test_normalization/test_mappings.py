"""Severity and category normalization tests."""

from app.normalization.category import normalize_event_name, normalize_gdacs_event_type
from app.normalization.severity import normalize_cap_severity, normalize_gdacs_alert_level
from app.schemas.common import Category, Severity


def test_cap_severity_mapping() -> None:
    assert normalize_cap_severity("Minor") == Severity.MINOR
    assert normalize_cap_severity("Severe") == Severity.SEVERE
    assert normalize_cap_severity(None) == Severity.UNKNOWN


def test_gdacs_alert_level_mapping() -> None:
    assert normalize_gdacs_alert_level("Green") == Severity.MINOR
    assert normalize_gdacs_alert_level("Orange", 2.5) == Severity.SEVERE
    assert normalize_gdacs_alert_level("Red", 3.5) == Severity.EXTREME


def test_event_name_category() -> None:
    assert normalize_event_name("Flood Advisory") == Category.FLOOD
    assert normalize_event_name("Severe Thunderstorm Warning") == Category.WEATHER


def test_gdacs_event_type() -> None:
    assert normalize_gdacs_event_type("EQ") == Category.EARTHQUAKE
    assert normalize_gdacs_event_type("TC") == Category.WEATHER
