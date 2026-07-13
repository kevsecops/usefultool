"""Space weather convenience API — filters noaa_swpc observed events."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import DataSource, Severity
from app.schemas.observed_event import ObservedEventListResponse, ObservedEventQueryParams
from app.services.observed_event_service import list_observed_events

router = APIRouter(prefix="/api/v1/space-weather", tags=["space-weather"])


@router.get("", response_model=ObservedEventListResponse)
def get_space_weather_events(
    severity: Severity | None = None,
    active: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_raw: bool = False,
    db: Session = Depends(get_db),
) -> ObservedEventListResponse:
    params = ObservedEventQueryParams(
        source=DataSource.NOAA_SWPC,
        severity=severity,
        active=active,
        limit=limit,
        offset=offset,
        include_raw=include_raw,
    )
    items, total = list_observed_events(db, params)
    return ObservedEventListResponse(items=items, total=total, limit=limit, offset=offset)
