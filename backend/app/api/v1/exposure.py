"""Exposure analysis API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.exposure import ExposureAnalysisResponse
from app.services.exposure_service import get_exposure_analysis

router = APIRouter(prefix="/api/v1/exposure", tags=["exposure"])


@router.get("/analysis", response_model=ExposureAnalysisResponse)
def get_exposure_analysis_endpoint(
    event_id: UUID = Query(..., description="Canonical event ID"),
    db: Session = Depends(get_db),
) -> ExposureAnalysisResponse:
    result = get_exposure_analysis(db, event_id)
    if not result:
        raise HTTPException(status_code=404, detail="Canonical event not found")
    return result
