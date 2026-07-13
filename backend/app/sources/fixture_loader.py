"""Fixture loader for DEMO_MODE."""

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_fixture(source: str, filename: str) -> Any:
    settings = get_settings()
    path = settings.fixtures_dir / source / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return _load_json(path)


def list_fixtures(source: str, pattern: str = "*.json") -> list[Path]:
    settings = get_settings()
    source_dir = settings.fixtures_dir / source
    if not source_dir.exists():
        return []
    return sorted(source_dir.glob(pattern))


def load_geojson(source: str, filename: str) -> dict[str, Any]:
    settings = get_settings()
    path = settings.fixtures_dir / source / filename
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON fixture not found: {path}")
    return _load_json(path)
