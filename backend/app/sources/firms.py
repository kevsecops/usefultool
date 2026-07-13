"""NASA FIRMS active-fire source adapter — clusters points during ingest."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.analysis.firms_clustering import (
    FireCluster,
    FirmsPoint,
    cluster_firms_points,
    cluster_to_metadata,
)
from app.core.config import get_settings
from app.core.http_client import HttpClient, HttpClientError
from app.core.logging import get_logger
from app.normalization.datetime_utils import utc_now
from app.schemas.common import (
    Category,
    Confidence,
    DataSource,
    ObservedEventStatus,
    Severity,
    SpatialScope,
)
from app.schemas.observed_event import CanonicalObservedEvent
from app.sources.base import ParsedObservedEvent, RawAlertPayload, SourceHealth
from app.sources.fixture_loader import list_fixtures, load_fixture

logger = get_logger(__name__)

_FIRMS_ALLOWED_HOSTS = frozenset({"firms.modaps.eosdis.nasa.gov"})

# Default: Southern Europe / Mediterranean wildfire-prone bbox (documented in docs/firms-mapping.md)
_DEFAULT_AREA_COORDS = "0,36,20,46"


def _firms_allowed_hosts(base_url: str) -> frozenset[str]:
    host = urlparse(base_url).hostname
    if host and host in _FIRMS_ALLOWED_HOSTS:
        return frozenset({host})
    return _FIRMS_ALLOWED_HOSTS


def parse_firms_acquired_at(acq_date: str | None, acq_time: str | None) -> datetime | None:
    """Parse FIRMS acq_date (YYYY-MM-DD) and acq_time (HHMM or HHMMSS)."""
    if not acq_date:
        return None
    time_part = (acq_time or "0000").strip()
    if len(time_part) == 4:
        time_part = f"{time_part}00"
    if len(time_part) < 6:
        time_part = time_part.ljust(6, "0")
    try:
        return datetime.strptime(f"{acq_date} {time_part[:6]}", "%Y-%m-%d %H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_firms_point_id(
    latitude: float,
    longitude: float,
    acq_date: str | None,
    acq_time: str | None,
    satellite: str | None,
) -> str:
    return f"firms-{latitude:.4f}-{longitude:.4f}-{acq_date or 'unknown'}-{acq_time or '0000'}-{satellite or 'unknown'}"


def parse_firms_csv(text: str) -> list[FirmsPoint]:
    """Parse NASA FIRMS area CSV into point records."""
    if not text.strip():
        return []

    reader = csv.DictReader(io.StringIO(text))
    points: list[FirmsPoint] = []
    for row in reader:
        lat = _safe_float(row.get("latitude"))
        lon = _safe_float(row.get("longitude"))
        if lat is None or lon is None:
            continue

        acq_date = row.get("acq_date")
        acq_time = row.get("acq_time")
        acquired_at = parse_firms_acquired_at(acq_date, acq_time) or utc_now()
        satellite = row.get("satellite")

        points.append(
            FirmsPoint(
                point_id=build_firms_point_id(lat, lon, acq_date, acq_time, satellite),
                latitude=lat,
                longitude=lon,
                acquired_at=acquired_at,
                brightness=_safe_float(row.get("brightness")),
                frp=_safe_float(row.get("frp")),
                confidence=row.get("confidence"),
                satellite=satellite,
                instrument=row.get("instrument"),
                scan=_safe_float(row.get("scan")),
                track=_safe_float(row.get("track")),
                daynight=row.get("daynight"),
            )
        )
    return points


def parse_firms_fixture_points(data: Any) -> list[FirmsPoint]:
    """Parse JSON fixture (list of point dicts) into FirmsPoint records."""
    if isinstance(data, dict) and isinstance(data.get("points"), list):
        rows = data["points"]
    elif isinstance(data, list):
        rows = data
    else:
        return []

    points: list[FirmsPoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lat = _safe_float(row.get("latitude"))
        lon = _safe_float(row.get("longitude"))
        if lat is None or lon is None:
            continue

        acq_date = row.get("acq_date")
        acq_time = row.get("acq_time")
        acquired_at = parse_firms_acquired_at(acq_date, acq_time)
        if acquired_at is None and row.get("acquired_at"):
            acquired_at = datetime.fromisoformat(str(row["acquired_at"]).replace("Z", "+00:00"))
        if acquired_at is None:
            acquired_at = utc_now()

        satellite = row.get("satellite")
        points.append(
            FirmsPoint(
                point_id=row.get("point_id")
                or build_firms_point_id(lat, lon, acq_date, acq_time, satellite),
                latitude=lat,
                longitude=lon,
                acquired_at=acquired_at,
                brightness=_safe_float(row.get("brightness")),
                frp=_safe_float(row.get("frp")),
                confidence=row.get("confidence"),
                satellite=satellite,
                instrument=row.get("instrument"),
                scan=_safe_float(row.get("scan")),
                track=_safe_float(row.get("track")),
                daynight=row.get("daynight"),
            )
        )
    return points


def refresh_firms_fixture_points(points: list[FirmsPoint], *, now: datetime | None = None) -> list[FirmsPoint]:
    """Shift fixture acquisition times so clusters stay within the configured time window."""
    now = now or utc_now()
    refreshed: list[FirmsPoint] = []
    for idx, point in enumerate(points):
        offset_hours = idx % 6
        refreshed.append(
            FirmsPoint(
                point_id=point.point_id,
                latitude=point.latitude,
                longitude=point.longitude,
                acquired_at=now - timedelta(hours=offset_hours),
                brightness=point.brightness,
                frp=point.frp,
                confidence=point.confidence,
                satellite=point.satellite,
                instrument=point.instrument,
                scan=point.scan,
                track=point.track,
                daynight=point.daynight,
            )
        )
    return refreshed


def build_cluster_title(cluster: FireCluster) -> str:
    return f"Active fire cluster ({len(cluster.points)} detections)"


def build_cluster_description(cluster: FireCluster) -> str:
    parts = [
        f"{len(cluster.points)} VIIRS/MODIS thermal anomalies aggregated",
        f"max FRP {cluster.maximum_frp:.1f} MW" if cluster.maximum_frp is not None else None,
        f"max brightness {cluster.maximum_brightness:.0f} K" if cluster.maximum_brightness is not None else None,
        f"satellites: {', '.join(cluster.satellite_sources)}" if cluster.satellite_sources else None,
    ]
    return ". ".join(p for p in parts if p)


def cluster_to_payload(cluster: FireCluster, ingest_mode: str) -> dict[str, Any]:
    """Cluster summary payload — no per-point raw rows."""
    return {
        "cluster_id": cluster.cluster_id,
        "point_count": len(cluster.points),
        "centroid_lat": cluster.centroid_lat,
        "centroid_lon": cluster.centroid_lon,
        "first_detected_at": cluster.first_detected_at.isoformat(),
        "last_detected_at": cluster.last_detected_at.isoformat(),
        "severity": cluster.severity,
        "confidence": cluster.confidence,
        "source_metadata": cluster_to_metadata(cluster),
        "_ingest_mode": ingest_mode,
    }


class FirmsSourceAdapter:
    source_id = DataSource.FIRMS
    record_type = "observed_event"

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.settings = get_settings()
        self._last_fetch: datetime | None = None
        self._last_ingest_mode: str | None = None
        self._last_raw_points_fetched: int = 0
        self._last_clusters_persisted: int = 0
        self._http = http_client or HttpClient(
            user_agent=self.settings.firms_user_agent,
            timeout_seconds=self.settings.firms_fetch_timeout_seconds,
            max_retries=self.settings.firms_max_retries,
            max_response_bytes=self.settings.firms_max_response_bytes,
            allowed_hosts=_firms_allowed_hosts(self.settings.firms_base_url),
        )

    @property
    def last_raw_points_fetched(self) -> int:
        return self._last_raw_points_fetched

    @property
    def last_clusters_persisted(self) -> int:
        return self._last_clusters_persisted

    def _use_fixtures(self) -> bool:
        if self.settings.demo_mode or self.settings.firms_use_fixtures:
            return True
        if not self.settings.firms_map_key:
            return True
        live_sources = {s.strip().lower() for s in self.settings.sources_live.split(",") if s.strip()}
        return "firms" not in live_sources

    def _cluster_points(self, points: list[FirmsPoint]) -> list[FireCluster]:
        self._last_raw_points_fetched = len(points)
        clusters = cluster_firms_points(
            points,
            grid_deg=self.settings.firms_cluster_grid_deg,
            time_hours=self.settings.firms_cluster_time_hours,
            min_cluster_points=self.settings.firms_min_cluster_points,
        )
        self._last_clusters_persisted = len(clusters)
        return clusters

    def _build_area_url(self) -> str:
        base = self.settings.firms_base_url.rstrip("/")
        product = self.settings.firms_product
        area = self.settings.firms_area_coords or _DEFAULT_AREA_COORDS
        day_range = self.settings.firms_day_range
        map_key = self.settings.firms_map_key
        return f"{base}/api/area/csv/{map_key}/{product}/{area}/{day_range}"

    async def _fetch_points_from_fixtures(self) -> list[FirmsPoint]:
        points: list[FirmsPoint] = []
        for path in list_fixtures("firms", "*.json"):
            data = load_fixture("firms", path.name, refresh_dates=False)
            fixture_points = parse_firms_fixture_points(data)
            points.extend(refresh_firms_fixture_points(fixture_points))
        self._last_fetch = utc_now()
        self._last_ingest_mode = "fixture"
        return points

    async def _fetch_points_live(self) -> list[FirmsPoint]:
        if not self.settings.firms_map_key:
            raise HttpClientError("FIRMS_MAP_KEY is required for live ingest")
        url = self._build_area_url()
        csv_text = await self._http.get_text(url)
        points = parse_firms_csv(csv_text)
        self._last_fetch = utc_now()
        self._last_ingest_mode = "live"
        logger.info("FIRMS live fetch returned %d raw points", len(points))
        return points

    async def fetch_alerts(self) -> list[RawAlertPayload]:
        if self._use_fixtures():
            points = await self._fetch_points_from_fixtures()
        else:
            try:
                points = await self._fetch_points_live()
            except Exception as exc:
                if self.settings.firms_fallback_to_fixtures and list_fixtures("firms", "*.json"):
                    logger.warning("FIRMS live fetch failed (%s), falling back to fixtures", exc)
                    points = await self._fetch_points_from_fixtures()
                else:
                    raise

        clusters = self._cluster_points(points)
        ingest_mode = self._last_ingest_mode or "live"
        logger.info(
            "FIRMS clustered %d raw points into %d clusters",
            self._last_raw_points_fetched,
            self._last_clusters_persisted,
        )
        return [
            RawAlertPayload(
                source=self.source_id,
                data=cluster_to_payload(cluster, ingest_mode),
                ingest_mode=ingest_mode,
            )
            for cluster in clusters
        ]

    def parse_observed_event(self, raw: RawAlertPayload) -> ParsedObservedEvent:
        cluster_id = str(raw.data.get("cluster_id", ""))
        return ParsedObservedEvent(
            source=self.source_id,
            source_event_id=cluster_id,
            fields={"cluster": raw.data},
            raw_payload=raw.data,
        )

    def normalize_observed_event(self, parsed: ParsedObservedEvent) -> CanonicalObservedEvent:
        cluster: dict[str, Any] = parsed.fields.get("cluster", {})
        metadata = cluster.get("source_metadata") or {}
        bounding = metadata.get("bounding_geometry")
        centroid = metadata.get("centroid") or {}
        coords = centroid.get("coordinates") if isinstance(centroid, dict) else None
        lon = coords[0] if isinstance(coords, list) and len(coords) >= 2 else cluster.get("centroid_lon")
        lat = coords[1] if isinstance(coords, list) and len(coords) >= 2 else cluster.get("centroid_lat")

        first_detected = cluster.get("first_detected_at")
        last_detected = cluster.get("last_detected_at")
        issued_at = datetime.fromisoformat(str(first_detected).replace("Z", "+00:00")) if first_detected else utc_now()
        ends_at = (
            datetime.fromisoformat(str(last_detected).replace("Z", "+00:00")) if last_detected else None
        )

        severity = cluster.get("severity", Severity.MODERATE)
        if isinstance(severity, str):
            severity = Severity(severity)

        confidence = cluster.get("confidence")
        if isinstance(confidence, str):
            confidence = Confidence(confidence)
        elif confidence is None:
            confidence = Confidence.MEDIUM

        point_count = metadata.get("point_count", cluster.get("point_count", 0))
        ingest_mode = cluster.get("_ingest_mode", "live")
        if isinstance(metadata, dict):
            metadata = {**metadata, "_ingest_mode": ingest_mode}

        return CanonicalObservedEvent(
            source=DataSource.FIRMS,
            source_event_id=parsed.source_event_id,
            source_url="https://firms.modaps.eosdis.nasa.gov/",
            title=build_cluster_title_from_count(point_count),
            description=build_cluster_description_from_metadata(metadata),
            event_type="active_fire_cluster",
            category=Category.WILDFIRE,
            severity=severity,
            status=ObservedEventStatus.AUTOMATIC,
            confidence=confidence,
            region=self.settings.firms_region_label,
            latitude=lat,
            longitude=lon,
            geometry=bounding,
            spatial_scope=SpatialScope.REGIONAL if point_count >= 10 else SpatialScope.LOCAL,
            issued_at=issued_at,
            starts_at=issued_at,
            ends_at=ends_at,
            updated_at_source=ends_at,
            raw_payload={
                "cluster_id": cluster.get("cluster_id"),
                "point_count": point_count,
                "_ingest_mode": ingest_mode,
            },
            source_metadata=metadata,
        )

    async def health_check(self) -> SourceHealth:
        now = utc_now()
        extra_metrics = {
            "raw_points_fetched": self._last_raw_points_fetched,
            "clusters_persisted": self._last_clusters_persisted,
        }
        if self._use_fixtures():
            fixtures = list_fixtures("firms", "*.json")
            if fixtures:
                return SourceHealth(
                    source=self.source_id,
                    is_healthy=True,
                    checked_at=now,
                    latency_ms=1,
                    last_success_at=self._last_fetch or now,
                    ingest_mode="fixture",
                    extra_metrics=extra_metrics,
                )
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                error_message="No FIRMS fixtures found",
                ingest_mode="fixture",
                extra_metrics=extra_metrics,
            )

        if not self.settings.firms_map_key:
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                error_message="FIRMS_MAP_KEY not configured",
                ingest_mode="live",
                extra_metrics=extra_metrics,
            )

        import time

        start = time.monotonic()
        try:
            status_url = f"{self.settings.firms_base_url.rstrip('/')}/api/map_key/{self.settings.firms_map_key}"
            await self._http.get_text(status_url)
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=True,
                checked_at=now,
                latency_ms=latency_ms,
                last_success_at=self._last_fetch or now,
                ingest_mode="live",
                extra_metrics=extra_metrics,
            )
        except (HttpClientError, Exception) as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return SourceHealth(
                source=self.source_id,
                is_healthy=False,
                checked_at=now,
                latency_ms=latency_ms,
                error_message=str(exc),
                ingest_mode="live",
                extra_metrics=extra_metrics,
            )


def build_cluster_title_from_count(point_count: int) -> str:
    return f"Active fire cluster ({point_count} detections)"


def build_cluster_description_from_metadata(metadata: dict[str, Any]) -> str:
    point_count = metadata.get("point_count", 0)
    frp = metadata.get("fire_radiative_power") or {}
    max_frp = frp.get("maximum") if isinstance(frp, dict) else None
    max_brightness = metadata.get("maximum_brightness")
    satellites = metadata.get("satellite_sources") or []
    parts = [f"{point_count} thermal anomalies aggregated into one cluster"]
    if max_frp is not None:
        parts.append(f"max FRP {max_frp:.1f} MW")
    if max_brightness is not None:
        parts.append(f"max brightness {max_brightness:.0f} K")
    if satellites:
        parts.append(f"satellites: {', '.join(satellites)}")
    return ". ".join(parts)
