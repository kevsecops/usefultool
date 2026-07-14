"""Rule-based geospatial exposure analysis against canonical events."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

from geoalchemy2.functions import ST_Contains, ST_DWithin, ST_GeomFromGeoJSON, ST_Intersects
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.alert import Alert
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.exposure_asset import ExposureAsset
from app.models.observed_event import ObservedEvent
from app.normalization.geometry import geojson_to_wkt_element
from app.schemas.exposure import ExposureType

ANALYSIS_VERSION = "1"

_SEVERITY_RADIUS_FACTOR = {
    "extreme": 1.5,
    "severe": 1.2,
    "moderate": 1.0,
    "minor": 0.8,
    "unknown": 0.9,
}

_SYSTEM_TO_ASSET_TYPES: dict[str, set[str]] = {
    "power_grid": {"power_plant"},
    "satellite_operations": {"airport", "port"},
    "gnss": {"airport"},
    "hf_radio": {"airport", "port"},
    "aviation": {"airport"},
}


@dataclass
class ExposureCandidate:
    asset_id: uuid.UUID
    exposure_type: str
    distance_km: float | None
    overlap: bool
    confidence: str
    rationale: str


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def earthquake_radius_km(
    magnitude: float,
    depth_km: float | None = None,
    severity: str = "moderate",
) -> float:
    """Heuristic felt/damage radius — NOT a scientific ground-motion model."""
    base = 10.0 * (1.8 ** max(magnitude - 4.0, 0.0))
    depth_factor = max(0.5, 1.0 - (depth_km or 10.0) / 300.0)
    severity_factor = _SEVERITY_RADIUS_FACTOR.get(severity, 1.0)
    return max(5.0, base * depth_factor * severity_factor)


def _extract_magnitude(metadata: dict[str, Any] | None) -> float | None:
    if not metadata:
        return None
    for key in ("magnitude", "mag"):
        value = metadata.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _extract_depth_km(metadata: dict[str, Any] | None) -> float | None:
    if not metadata:
        return None
    for key in ("depth_km", "depth"):
        value = metadata.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _load_primary_member(
    db: Session, event: CanonicalEvent
) -> tuple[Alert | ObservedEvent | None, str | None]:
    """Return primary linked member and its source."""
    if not event.links:
        return None, None
    primary_link = next(
        (link for link in event.links if link.member_id == event.primary_source_id),
        event.links[0],
    )
    if primary_link.member_type == "alert":
        member = db.get(Alert, primary_link.member_id)
    else:
        member = db.get(ObservedEvent, primary_link.member_id)
    source = getattr(member, "source", None) if member else None
    return member, source


def _member_metadata(member: Alert | ObservedEvent | None) -> dict[str, Any]:
    if member is None:
        return {}
    if isinstance(member, ObservedEvent):
        return member.source_metadata or {}
    raw = member.raw_payload or {}
    props = raw.get("properties", raw) if isinstance(raw, dict) else {}
    return props if isinstance(props, dict) else {}


def _member_geometry_json(member: Alert | ObservedEvent | None, event: CanonicalEvent) -> dict | None:
    if member and member.geometry_json:
        return member.geometry_json
    return event.geometry_json


def _analyze_earthquake(
    db: Session,
    event: CanonicalEvent,
    member: Alert | ObservedEvent | None,
    buffer_km: float,
) -> list[ExposureCandidate]:
    metadata = _member_metadata(member)
    magnitude = _extract_magnitude(metadata)
    if magnitude is None and member:
        title = getattr(member, "title", "") or ""
        import re

        match = re.search(r"M\s*([\d.]+)", title, re.IGNORECASE)
        if match:
            magnitude = float(match.group(1))
    if magnitude is None:
        magnitude = 4.5

    depth = _extract_depth_km(metadata)
    radius = earthquake_radius_km(magnitude, depth, event.severity)
    near_radius = radius + buffer_km

    lat = getattr(member, "latitude", None) if member else None
    lon = getattr(member, "longitude", None) if member else None
    if lat is None or lon is None:
        geom = _member_geometry_json(member, event)
        if geom and geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

    if lat is None or lon is None:
        return []

    assets = db.scalars(
        select(ExposureAsset).where(
            ExposureAsset.latitude.isnot(None),
            ExposureAsset.longitude.isnot(None),
        )
    ).all()

    candidates: list[ExposureCandidate] = []
    for asset in assets:
        assert asset.latitude is not None and asset.longitude is not None
        distance = _haversine_km(lat, lon, asset.latitude, asset.longitude)
        if distance <= radius:
            candidates.append(
                ExposureCandidate(
                    asset_id=asset.id,
                    exposure_type=ExposureType.INSIDE_EVENT_AREA,
                    distance_km=round(distance, 2),
                    overlap=True,
                    confidence="high" if distance <= radius * 0.5 else "medium",
                    rationale=(
                        f"Earthquake M{magnitude:.1f} heuristic radius {radius:.0f} km "
                        f"(depth={depth or 'unknown'} km, severity={event.severity})"
                    ),
                )
            )
        elif distance <= near_radius:
            candidates.append(
                ExposureCandidate(
                    asset_id=asset.id,
                    exposure_type=ExposureType.NEAR_EVENT_AREA,
                    distance_km=round(distance, 2),
                    overlap=False,
                    confidence="medium",
                    rationale=(
                        f"Within {buffer_km:.0f} km buffer of M{magnitude:.1f} "
                        f"heuristic radius ({radius:.0f} km)"
                    ),
                )
            )
    return candidates


def _analyze_polygon_event(
    db: Session,
    event: CanonicalEvent,
    member: Alert | ObservedEvent | None,
    buffer_km: float,
    event_label: str,
) -> list[ExposureCandidate]:
    geom_json = _member_geometry_json(member, event)
    if not geom_json:
        return []

    wkt = geojson_to_wkt_element(geom_json)
    if wkt is None:
        return []

    inside_assets = db.scalars(
        select(ExposureAsset).where(
            ExposureAsset.geometry.isnot(None),
            ST_Contains(wkt, ExposureAsset.geometry),
        )
    ).all()

    candidates: list[ExposureCandidate] = []
    seen_ids: set[uuid.UUID] = set()

    for asset in inside_assets:
        seen_ids.add(asset.id)
        candidates.append(
            ExposureCandidate(
                asset_id=asset.id,
                exposure_type=ExposureType.INSIDE_EVENT_AREA,
                distance_km=0.0,
                overlap=True,
                confidence="high",
                rationale=f"Asset inside {event_label} event geometry (ST_Contains)",
            )
        )

    near_assets = db.scalars(
        select(ExposureAsset).where(
            ExposureAsset.geometry.isnot(None),
            ~ExposureAsset.id.in_(seen_ids) if seen_ids else True,
            ST_DWithin(
                ExposureAsset.geometry,
                wkt,
                buffer_km / 111.32,
            ),
        )
    ).all()

    for asset in near_assets:
        candidates.append(
            ExposureCandidate(
                asset_id=asset.id,
                exposure_type=ExposureType.NEAR_EVENT_AREA,
                distance_km=None,
                overlap=False,
                confidence="medium",
                rationale=(
                    f"Asset within {buffer_km:.0f} km buffer of {event_label} event geometry"
                ),
            )
        )

    return candidates


def _analyze_fire_cluster(
    db: Session,
    event: CanonicalEvent,
    member: ObservedEvent | None,
    buffer_km: float,
) -> list[ExposureCandidate]:
    geom_json = None
    if member and member.source_metadata:
        geom_json = member.source_metadata.get("bounding_geometry")
    if not geom_json:
        geom_json = _member_geometry_json(member, event)
    if not geom_json:
        return []

    wkt = geojson_to_wkt_element(geom_json)
    if wkt is None:
        return []

    inside = db.scalars(
        select(ExposureAsset).where(
            ExposureAsset.geometry.isnot(None),
            ST_Intersects(ExposureAsset.geometry, wkt),
        )
    ).all()

    candidates: list[ExposureCandidate] = []
    seen: set[uuid.UUID] = set()
    for asset in inside:
        seen.add(asset.id)
        candidates.append(
            ExposureCandidate(
                asset_id=asset.id,
                exposure_type=ExposureType.INSIDE_EVENT_AREA,
                distance_km=0.0,
                overlap=True,
                confidence="high",
                rationale="Asset inside FIRMS fire cluster bounding geometry",
            )
        )

    near = db.scalars(
        select(ExposureAsset).where(
            ExposureAsset.geometry.isnot(None),
            ~ExposureAsset.id.in_(seen) if seen else True,
            ST_DWithin(ExposureAsset.geometry, wkt, buffer_km / 111.32),
        )
    ).all()
    for asset in near:
        candidates.append(
            ExposureCandidate(
                asset_id=asset.id,
                exposure_type=ExposureType.NEAR_EVENT_AREA,
                distance_km=None,
                overlap=False,
                confidence="medium",
                rationale=f"Asset within {buffer_km:.0f} km of fire cluster bounding box",
            )
        )
    return candidates


def _relevant_asset_types(potential_systems: list[str]) -> set[str]:
    types: set[str] = set()
    for system in potential_systems:
        types.update(_SYSTEM_TO_ASSET_TYPES.get(system, set()))
    return types


def _analyze_space_weather(
    db: Session,
    event: CanonicalEvent,
    member: ObservedEvent | None,
) -> list[ExposureCandidate]:
    metadata = _member_metadata(member)
    potential_systems = metadata.get("potential_systems", [])
    if not potential_systems and member and isinstance(member, ObservedEvent):
        potential_systems = (member.source_metadata or {}).get("potential_systems", [])

    asset_types = _relevant_asset_types(potential_systems)
    if not asset_types:
        asset_types = {"power_plant", "airport", "port"}

    spatial_scope = event.spatial_scope
    if member and isinstance(member, ObservedEvent):
        spatial_scope = member.spatial_scope or spatial_scope

    lat_min = getattr(member, "affected_latitude_min", None) if member else None
    lat_max = getattr(member, "affected_latitude_max", None) if member else None

    query = select(ExposureAsset).where(ExposureAsset.asset_type.in_(asset_types))
    if lat_min is not None:
        query = query.where(ExposureAsset.latitude >= lat_min)
    if lat_max is not None:
        query = query.where(ExposureAsset.latitude <= lat_max)

    assets = db.scalars(query).all()
    systems_label = ", ".join(potential_systems) or "general space weather"
    candidates: list[ExposureCandidate] = []

    for asset in assets:
        rationale = (
            f"System-level exposure: {asset.asset_type} relevant to [{systems_label}] "
            f"under {spatial_scope} scope"
        )
        if lat_min is not None:
            rationale += f" (latitude >= {lat_min}°)"
        candidates.append(
            ExposureCandidate(
                asset_id=asset.id,
                exposure_type=ExposureType.SYSTEM_LEVEL_EXPOSURE,
                distance_km=None,
                overlap=False,
                confidence="medium" if spatial_scope in ("global", "orbital") else "low",
                rationale=rationale,
            )
        )
    return candidates


def _is_storm_event(event_type: str | None, category: str | None, source: str | None) -> bool:
    storm_types = {"storm", "tropical_cyclone", "cyclone", "hurricane", "typhoon", "flood", "weather"}
    if event_type and event_type.lower() in storm_types:
        return True
    if category and category.lower() in {"weather", "flood", "tsunami"}:
        return True
    return source in ("gdacs", "eonet", "noaa")


def analyze_event_exposure(
    db: Session,
    event: CanonicalEvent,
    *,
    buffer_km: float | None = None,
) -> list[ExposureCandidate]:
    """Compute exposure candidates for a canonical event."""
    settings = get_settings()
    buffer = buffer_km if buffer_km is not None else settings.exposure_buffer_km

    member, source = _load_primary_member(db, event)
    event_type = (event.event_type or "").lower()
    category = None
    if member:
        category = getattr(member, "category", None)

    if event_type == "earthquake" or (category == "earthquake"):
        return _analyze_earthquake(db, event, member, buffer)

    if event_type == "active_fire_cluster" or (category == "wildfire" and source == "firms"):
        obs_member = member if isinstance(member, ObservedEvent) else None
        return _analyze_fire_cluster(db, event, obs_member, buffer)

    if source == "noaa_swpc" or event_type in ("geomagnetic_storm", "solar_radiation_storm", "radio_blackout"):
        obs_member = member if isinstance(member, ObservedEvent) else None
        if obs_member is None and event.links:
            for link in event.links:
                if link.member_type == "observed_event":
                    obs_member = db.get(ObservedEvent, link.member_id)
                    if obs_member and obs_member.source == "noaa_swpc":
                        break
        return _analyze_space_weather(db, event, obs_member)

    geom_json = _member_geometry_json(member, event)
    if geom_json and geom_json.get("type") in ("Polygon", "MultiPolygon"):
        label = event_type or category or "polygon"
        return _analyze_polygon_event(db, event, member, buffer, label)

    if _is_storm_event(event_type, category, source):
        return _analyze_polygon_event(db, event, member, buffer, event_type or "storm")

    if geom_json and geom_json.get("type") == "Point":
        return _analyze_earthquake(db, event, member, buffer)

    return []


def count_assets_near_point(
    db: Session,
    lat: float,
    lon: float,
    radius_km: float,
) -> int:
    """Utility for tests — count assets within haversine radius."""
    assets = db.scalars(
        select(ExposureAsset).where(
            ExposureAsset.latitude.isnot(None),
            ExposureAsset.longitude.isnot(None),
        )
    ).all()
    return sum(
        1
        for asset in assets
        if asset.latitude is not None
        and asset.longitude is not None
        and _haversine_km(lat, lon, asset.latitude, asset.longitude) <= radius_km
    )


def count_assets_in_geometry(db: Session, geojson: dict) -> int:
    """Utility for tests — count assets inside geometry."""
    wkt = geojson_to_wkt_element(geojson)
    if wkt is None:
        return 0
    return (
        db.scalar(
            select(func.count())
            .select_from(ExposureAsset)
            .where(
                ExposureAsset.geometry.isnot(None),
                ST_Contains(wkt, ExposureAsset.geometry),
            )
        )
        or 0
    )
