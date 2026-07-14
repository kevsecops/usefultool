"""Exposure asset management and geospatial analysis orchestration."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, selectinload

from app.analysis.exposure_analysis import ANALYSIS_VERSION, analyze_event_exposure
from app.core.config import get_settings
from app.models.canonical_event import CanonicalEvent
from app.models.event_asset_exposure import EventAssetExposure
from app.models.exposure_asset import ExposureAsset
from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box
from app.normalization.datetime_utils import utc_now
from app.normalization.geometry import geojson_to_wkt_element
from app.schemas.exposure import (
    AssetQueryParams,
    AssetResponse,
    CalculateExposureResponse,
    EventAssetExposureResponse,
    EventExposureListResponse,
    ExposureAnalysisResponse,
    ImportExposureResponse,
)

_FIXTURE_FILES = {
    "port": "ports.json",
    "airport": "airports.json",
    "power_plant": "power_plants.json",
}


@dataclass
class CalculateStats:
    events_processed: int = 0
    exposures_created: int = 0
    exposures_updated: int = 0


def _asset_to_response(asset: ExposureAsset) -> AssetResponse:
    fields = {col.key: getattr(asset, col.key) for col in inspect(asset).mapper.column_attrs}
    if "metadata_" in fields:
        fields["metadata"] = fields.pop("metadata_")
    elif "metadata" not in fields:
        fields["metadata"] = asset.metadata_
    fields.pop("geometry", None)
    return AssetResponse.model_validate(fields)


def _exposure_to_response(
    exposure: EventAssetExposure, include_asset: bool = True
) -> EventAssetExposureResponse:
    fields = {col.key: getattr(exposure, col.key) for col in inspect(exposure).mapper.column_attrs}
    asset_data = None
    if include_asset and exposure.asset:
        asset_data = _asset_to_response(exposure.asset)
    fields["asset"] = asset_data
    return EventAssetExposureResponse.model_validate(fields)


def list_assets(db: Session, params: AssetQueryParams) -> tuple[list[AssetResponse], int]:
    query = select(ExposureAsset)
    count_query = select(func.count()).select_from(ExposureAsset)

    if params.asset_type:
        query = query.where(ExposureAsset.asset_type == params.asset_type)
        count_query = count_query.where(ExposureAsset.asset_type == params.asset_type)
    if params.country_code:
        query = query.where(ExposureAsset.country_code == params.country_code.upper())
        count_query = count_query.where(ExposureAsset.country_code == params.country_code.upper())
    if params.bounding_box:
        try:
            bbox = parse_bounding_box(params.bounding_box)
        except BoundingBoxError:
            raise
        envelope = ST_MakeEnvelope(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, 4326)
        geo_filter = ExposureAsset.geometry.isnot(None) & ST_Intersects(
            ExposureAsset.geometry, envelope
        )
        query = query.where(geo_filter)
        count_query = count_query.where(geo_filter)

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(ExposureAsset.name).limit(params.limit).offset(params.offset)
    ).all()
    return [_asset_to_response(row) for row in rows], total


def get_asset(db: Session, asset_id: uuid.UUID) -> AssetResponse | None:
    asset = db.get(ExposureAsset, asset_id)
    if not asset:
        return None
    return _asset_to_response(asset)


def import_exposure_fixtures(db: Session) -> ImportExposureResponse:
    """Load demo fixtures from fixtures/exposure/."""
    settings = get_settings()
    exposure_dir = settings.fixtures_dir / "exposure"
    created = 0
    updated = 0
    now = utc_now()

    for asset_type, filename in _FIXTURE_FILES.items():
        path = exposure_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            records = json.load(f)

        for record in records:
            source_asset_id = record["source_asset_id"]
            existing = db.scalar(
                select(ExposureAsset).where(
                    ExposureAsset.source == "demo_fixture",
                    ExposureAsset.source_asset_id == source_asset_id,
                )
            )
            lat = record.get("latitude")
            lon = record.get("longitude")
            point_geojson = (
                {"type": "Point", "coordinates": [lon, lat]} if lat is not None and lon is not None else None
            )
            geometry = geojson_to_wkt_element(point_geojson)

            if existing:
                existing.name = record["name"]
                existing.country_code = record.get("country_code")
                existing.region = record.get("region")
                existing.latitude = lat
                existing.longitude = lon
                existing.geometry = geometry
                existing.importance_level = record.get("importance_level", "medium")
                existing.metadata_ = record.get("metadata")
                existing.updated_at = now
                updated += 1
            else:
                db.add(
                    ExposureAsset(
                        asset_type=asset_type,
                        name=record["name"],
                        country_code=record.get("country_code"),
                        region=record.get("region"),
                        latitude=lat,
                        longitude=lon,
                        geometry=geometry,
                        importance_level=record.get("importance_level", "medium"),
                        source="demo_fixture",
                        source_url=None,
                        source_asset_id=source_asset_id,
                        metadata_=record.get("metadata"),
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1

    db.flush()
    total = db.scalar(select(func.count()).select_from(ExposureAsset)) or 0
    return ImportExposureResponse(
        assets_created=created,
        assets_updated=updated,
        total_assets=total,
    )


def calculate_exposure_for_event(
    db: Session,
    event_id: uuid.UUID,
) -> tuple[int, int]:
    """Analyze and persist exposures for one canonical event. Returns (created, updated)."""
    event = db.scalar(
        select(CanonicalEvent)
        .options(selectinload(CanonicalEvent.links))
        .where(CanonicalEvent.id == event_id)
    )
    if not event:
        return 0, 0

    candidates = analyze_event_exposure(db, event)
    now = utc_now()
    created = 0
    updated = 0

    existing_map = {
        row.asset_id: row
        for row in db.scalars(
            select(EventAssetExposure).where(EventAssetExposure.event_id == event_id)
        ).all()
    }

    seen_asset_ids: set[uuid.UUID] = set()
    for candidate in candidates:
        seen_asset_ids.add(candidate.asset_id)
        existing = existing_map.get(candidate.asset_id)
        if existing:
            existing.exposure_type = candidate.exposure_type
            existing.distance_km = candidate.distance_km
            existing.overlap = candidate.overlap
            existing.confidence = candidate.confidence
            existing.rationale = candidate.rationale
            existing.calculated_at = now
            existing.analysis_version = ANALYSIS_VERSION
            updated += 1
        else:
            db.add(
                EventAssetExposure(
                    event_id=event_id,
                    asset_id=candidate.asset_id,
                    exposure_type=candidate.exposure_type,
                    distance_km=candidate.distance_km,
                    overlap=candidate.overlap,
                    confidence=candidate.confidence,
                    rationale=candidate.rationale,
                    calculated_at=now,
                    analysis_version=ANALYSIS_VERSION,
                )
            )
            created += 1

    db.flush()
    return created, updated


def run_calculate_exposure(
    db: Session,
    *,
    event_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> CalculateExposureResponse:
    """Run exposure analysis for one or all canonical events."""
    stats = CalculateStats()

    if event_id:
        event_ids = [event_id]
    else:
        query = select(CanonicalEvent.id)
        if active_only:
            query = query.where(CanonicalEvent.is_active.is_(True))
        event_ids = list(db.scalars(query).all())

    for eid in event_ids:
        if not db.get(CanonicalEvent, eid):
            continue
        created, updated = calculate_exposure_for_event(db, eid)
        stats.events_processed += 1
        stats.exposures_created += created
        stats.exposures_updated += updated

    return CalculateExposureResponse(
        events_processed=stats.events_processed,
        exposures_created=stats.exposures_created,
        exposures_updated=stats.exposures_updated,
        analysis_version=ANALYSIS_VERSION,
    )


def list_event_exposures(
    db: Session,
    event_id: uuid.UUID,
) -> EventExposureListResponse | None:
    event = db.get(CanonicalEvent, event_id)
    if not event:
        return None

    rows = db.scalars(
        select(EventAssetExposure)
        .options(selectinload(EventAssetExposure.asset))
        .where(EventAssetExposure.event_id == event_id)
        .order_by(EventAssetExposure.confidence.desc())
    ).all()

    items = [_exposure_to_response(row) for row in rows]
    return EventExposureListResponse(event_id=event_id, items=items, total=len(items))


def get_exposure_analysis(
    db: Session,
    event_id: uuid.UUID,
) -> ExposureAnalysisResponse | None:
    event = db.get(CanonicalEvent, event_id)
    if not event:
        return None

    exposure_list = list_event_exposures(db, event_id)
    assert exposure_list is not None

    return ExposureAnalysisResponse(
        event_id=event_id,
        event_type=event.event_type,
        event_title=event.title,
        exposures=exposure_list.items,
        total=exposure_list.total,
        analysis_version=ANALYSIS_VERSION,
    )
