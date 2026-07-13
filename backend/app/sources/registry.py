"""Source adapter registry."""

from app.core.config import get_settings
from app.sources.base import BaseSourceAdapter
from app.sources.gdacs import GdacsSourceAdapter
from app.sources.nina import NinaSourceAdapter
from app.sources.noaa import NoaaSourceAdapter

_ADAPTERS: dict[str, type] = {
    "nina": NinaSourceAdapter,
    "gdacs": GdacsSourceAdapter,
    "noaa": NoaaSourceAdapter,
}


def get_adapters(sources: list[str] | None = None) -> list[BaseSourceAdapter]:
    settings = get_settings()
    if not settings.demo_mode:
        # Phase 2: fixture-only; live fetch deferred to Phase 3
        pass
    source_ids = sources or list(_ADAPTERS.keys())
    return [_ADAPTERS[s]() for s in source_ids if s in _ADAPTERS]


def get_adapter(source_id: str) -> BaseSourceAdapter:
    if source_id not in _ADAPTERS:
        raise ValueError(f"Unknown source: {source_id}")
    return _ADAPTERS[source_id]()
