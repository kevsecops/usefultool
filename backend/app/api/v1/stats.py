"""Stats API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.stats import StatsResponse
from app.services.stats_service import get_stats

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def read_stats(db: Session = Depends(get_db)) -> StatsResponse:
    return get_stats(db)
