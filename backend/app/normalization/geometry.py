"""Geometry helpers."""

import json
from typing import Any

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import from_shape
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


def geojson_to_wkt_element(geojson: dict[str, Any] | None) -> WKTElement | None:
    if not geojson:
        return None
    try:
        geom: BaseGeometry = shape(geojson)
        return from_shape(geom, srid=4326)
    except Exception:
        return None


def wkt_element_to_geojson(wkt_elem: Any) -> dict[str, Any] | None:
    if wkt_elem is None:
        return None
    try:
        from geoalchemy2.shape import to_shape

        geom = to_shape(wkt_elem)
        return mapping(geom)
    except Exception:
        return None


def compute_centroid(geojson: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not geojson:
        return None, None
    try:
        geom = shape(geojson)
        centroid = geom.centroid
        return centroid.y, centroid.x
    except Exception:
        return None, None


def geojson_to_json_string(geojson: dict[str, Any] | None) -> str | None:
    if not geojson:
        return None
    return json.dumps(geojson)
