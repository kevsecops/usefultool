"""Bounding box parsing tests."""

import pytest

from app.normalization.bounding_box import BoundingBoxError, parse_bounding_box


def test_parse_valid_bounding_box() -> None:
    bbox = parse_bounding_box("-98.0,32.0,-96.0,34.0")
    assert bbox.min_lon == -98.0
    assert bbox.min_lat == 32.0
    assert bbox.max_lon == -96.0
    assert bbox.max_lat == 34.0


def test_parse_rejects_wrong_count() -> None:
    with pytest.raises(BoundingBoxError, match="4 comma-separated"):
        parse_bounding_box("-98,32,-96")


def test_parse_rejects_invalid_longitude() -> None:
    with pytest.raises(BoundingBoxError, match="longitude"):
        parse_bounding_box("200,32,-96,34")


def test_parse_rejects_inverted_bounds() -> None:
    with pytest.raises(BoundingBoxError, match="min_lon"):
        parse_bounding_box("-96,32,-98,34")
