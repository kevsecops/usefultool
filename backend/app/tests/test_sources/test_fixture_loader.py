"""Tests for fixture datetime refresh."""

from datetime import UTC, datetime

from app.sources.fixture_loader import refresh_fixture_datetimes


def test_refresh_fixture_datetimes_rewrites_known_fields() -> None:
    now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    payload = {
        "sent": "2026-01-13T11:09:37+00:00",
        "info": [
            {
                "effective": "2026-01-13T11:09:37+00:00",
                "onset": "2026-01-13T12:00:00+00:00",
                "expires": "2026-01-14T06:00:00+00:00",
            }
        ],
        "properties": {
            "fromdate": "2026-07-10T00:00:00",
            "todate": "2026-07-20T00:00:00",
        },
    }

    refreshed = refresh_fixture_datetimes(payload, now=now)

    assert refreshed["sent"] == "2026-07-13T10:00:00Z"
    assert refreshed["info"][0]["expires"] == "2026-07-14T12:00:00Z"
    assert refreshed["properties"]["fromdate"] == "2026-07-13T10:00:00Z"
    assert refreshed["properties"]["todate"] == "2026-07-14T12:00:00Z"
