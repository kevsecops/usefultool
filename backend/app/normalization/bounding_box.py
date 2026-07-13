"""Bounding box parsing for geo queries."""

from dataclasses import dataclass


class BoundingBoxError(ValueError):
    """Raised when bounding_box query param is invalid."""


@dataclass(frozen=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


def parse_bounding_box(value: str) -> BoundingBox:
    """Parse `min_lon,min_lat,max_lon,max_lat` into a validated BoundingBox."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise BoundingBoxError("bounding_box must have exactly 4 comma-separated values")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise BoundingBoxError("bounding_box values must be numeric") from exc

    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise BoundingBoxError("longitude must be between -180 and 180")
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise BoundingBoxError("latitude must be between -90 and 90")
    if min_lon >= max_lon:
        raise BoundingBoxError("min_lon must be less than max_lon")
    if min_lat >= max_lat:
        raise BoundingBoxError("min_lat must be less than max_lat")

    return BoundingBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)
