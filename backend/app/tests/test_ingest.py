"""Ingest service tests."""

import pytest
from sqlalchemy import func, select

from app.models.alert import Alert
from app.services.ingest_service import run_ingest


@pytest.mark.asyncio
async def test_ingest_populates_alerts(db_session) -> None:
    run = await run_ingest(db_session)
    db_session.commit()
    assert run.status in ("success", "partial")
    assert run.alerts_fetched > 0
    assert run.alerts_created > 0

    count = db_session.scalar(select(func.count()).select_from(Alert))
    assert count == run.alerts_created


@pytest.mark.asyncio
async def test_ingest_is_idempotent(db_session) -> None:
    await run_ingest(db_session)
    db_session.commit()
    run2 = await run_ingest(db_session)
    db_session.commit()
    assert run2.alerts_created == 0
    assert run2.alerts_updated >= 0
