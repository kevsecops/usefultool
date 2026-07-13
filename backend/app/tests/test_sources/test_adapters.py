"""Source adapter tests."""

import pytest

from app.sources.gdacs import GdacsSourceAdapter
from app.sources.nina import NinaSourceAdapter
from app.sources.noaa import NoaaSourceAdapter


@pytest.mark.asyncio
async def test_nina_fetch_and_normalize() -> None:
    adapter = NinaSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) >= 3
    canonical = adapter.normalize_alert(adapter.parse_alert(raw_alerts[0]))
    assert canonical.source == "nina"
    assert canonical.country_code == "DE"
    assert canonical.title


@pytest.mark.asyncio
async def test_gdacs_fetch_and_normalize() -> None:
    adapter = GdacsSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) == 3
    canonical = adapter.normalize_alert(adapter.parse_alert(raw_alerts[0]))
    assert canonical.source == "gdacs"
    assert canonical.category == "earthquake"


@pytest.mark.asyncio
async def test_noaa_fetch_and_normalize() -> None:
    adapter = NoaaSourceAdapter()
    raw_alerts = await adapter.fetch_alerts()
    assert len(raw_alerts) >= 2
    canonical = adapter.normalize_alert(adapter.parse_alert(raw_alerts[0]))
    assert canonical.source == "noaa"
    assert canonical.country_code == "US"
