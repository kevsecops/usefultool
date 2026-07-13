"""Fingerprint generation tests."""

from datetime import UTC, datetime

from app.normalization.fingerprint import generate_fingerprint
from app.schemas.common import AlertSource, Category, Severity


def test_fingerprint_deterministic() -> None:
    issued = datetime(2026, 7, 13, 10, 0, 0, tzinfo=UTC)
    fp1 = generate_fingerprint(
        source=AlertSource.NOAA,
        source_alert_id="urn:oid:123",
        title="Flood Advisory",
        issued_at=issued,
        severity=Severity.MINOR,
        category=Category.FLOOD,
    )
    fp2 = generate_fingerprint(
        source=AlertSource.NOAA,
        source_alert_id="urn:oid:123",
        title="Flood Advisory",
        issued_at=issued,
        severity=Severity.MINOR,
        category=Category.FLOOD,
    )
    assert fp1 == fp2
    assert len(fp1) == 64


def test_fingerprint_differs_on_title_change() -> None:
    issued = datetime(2026, 7, 13, 10, 0, 0, tzinfo=UTC)
    fp1 = generate_fingerprint(
        source=AlertSource.NOAA,
        source_alert_id="urn:oid:123",
        title="Flood Advisory",
        issued_at=issued,
        severity=Severity.MINOR,
        category=Category.FLOOD,
    )
    fp2 = generate_fingerprint(
        source=AlertSource.NOAA,
        source_alert_id="urn:oid:123",
        title="Flood Warning",
        issued_at=issued,
        severity=Severity.MINOR,
        category=Category.FLOOD,
    )
    assert fp1 != fp2
