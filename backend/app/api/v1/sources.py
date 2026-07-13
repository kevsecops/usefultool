"""Sources API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.sources import SourcesResponse
from app.services.source_service import get_sources

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("", response_model=SourcesResponse)
async def list_sources(db: Session = Depends(get_db)) -> SourcesResponse:
    return await get_sources(db)
