"""Exposure assets API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.exposure import AssetListResponse, AssetQueryParams, AssetResponse, AssetType
from app.services.exposure_service import get_asset, list_assets

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("", response_model=AssetListResponse)
def get_assets(
    asset_type: AssetType | None = None,
    country_code: str | None = None,
    bounding_box: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AssetListResponse:
    from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box

    if bounding_box:
        try:
            parse_bounding_box(bounding_box)
        except BoundingBoxError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    params = AssetQueryParams(
        asset_type=asset_type,
        country_code=country_code,
        bounding_box=bounding_box,
        limit=limit,
        offset=offset,
    )
    items, total = list_assets(db, params)
    return AssetListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset_by_id(
    asset_id: UUID,
    db: Session = Depends(get_db),
) -> AssetResponse:
    asset = get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset
