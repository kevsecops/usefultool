"""Exposure asset and analysis Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Confidence


class AssetType(StrEnum):
    PORT = "port"
    AIRPORT = "airport"
    POWER_PLANT = "power_plant"


class ImportanceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExposureType(StrEnum):
    INSIDE_EVENT_AREA = "inside_event_area"
    NEAR_EVENT_AREA = "near_event_area"
    SYSTEM_LEVEL_EXPOSURE = "system_level_exposure"
    UNKNOWN = "unknown"


class AssetQueryParams(BaseModel):
    asset_type: AssetType | None = None
    country_code: str | None = None
    bounding_box: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_type: str
    name: str
    country_code: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    importance_level: str
    source: str
    source_url: str | None = None
    source_asset_id: str | None = None
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    limit: int
    offset: int


class EventAssetExposureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    asset_id: UUID
    exposure_type: ExposureType
    distance_km: float | None = None
    overlap: bool
    confidence: Confidence
    rationale: str | None = None
    calculated_at: datetime
    analysis_version: str
    asset: AssetResponse | None = None


class EventExposureListResponse(BaseModel):
    event_id: UUID
    items: list[EventAssetExposureResponse]
    total: int


class CalculateExposureRequest(BaseModel):
    event_id: UUID | None = None
    active_only: bool = True


class CalculateExposureResponse(BaseModel):
    events_processed: int
    exposures_created: int
    exposures_updated: int
    analysis_version: str


class ImportExposureResponse(BaseModel):
    assets_created: int
    assets_updated: int
    total_assets: int


class ExposureAnalysisResponse(BaseModel):
    event_id: UUID
    event_type: str | None = None
    event_title: str
    exposures: list[EventAssetExposureResponse]
    total: int
    analysis_version: str
