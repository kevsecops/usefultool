"""Source adapter registry."""

from app.sources.base import BaseSourceAdapter
from app.sources.eonet import EonetSourceAdapter
from app.sources.firms import FirmsSourceAdapter
from app.sources.gdacs import GdacsSourceAdapter
from app.sources.nina import NinaSourceAdapter
from app.sources.noaa import NoaaSourceAdapter
from app.sources.noaa_swpc import NoaaSwpcSourceAdapter
from app.sources.usgs import UsgsSourceAdapter

_ADAPTERS: dict[str, type] = {
    "nina": NinaSourceAdapter,
    "gdacs": GdacsSourceAdapter,
    "noaa": NoaaSourceAdapter,
    "usgs": UsgsSourceAdapter,
    "eonet": EonetSourceAdapter,
    "noaa_swpc": NoaaSwpcSourceAdapter,
    "firms": FirmsSourceAdapter,
}


def get_adapters(sources: list[str] | None = None) -> list[BaseSourceAdapter]:
    source_ids = sources or list(_ADAPTERS.keys())
    return [_ADAPTERS[s]() for s in source_ids if s in _ADAPTERS]


def get_adapter(source_id: str) -> BaseSourceAdapter:
    if source_id not in _ADAPTERS:
        raise ValueError(f"Unknown source: {source_id}")
    return _ADAPTERS[source_id]()
