# FIRMS Fire Clustering

> **Phase 3** — Aggregation of NASA FIRMS thermal anomaly **points** into `active_fire_cluster` observed events.

## Problem

FIRMS area API returns hundreds to thousands of point detections per request. Storing, displaying, or sending each point to an LLM would be unusable. Phase 3 clusters points **during ingest** and persists **only clusters** as `observed_events`.

## Algorithm (v1)

**Grid + time-bucket grouping** — transparent, deterministic, no ML.

1. Assign each point a grid cell: `(floor(lat / grid_deg), floor(lon / grid_deg))`
2. Assign each point a time bucket: `floor(epoch_hours / time_hours)`
3. Group key: `(grid_lat, grid_lon, time_bucket)`
4. Drop groups with fewer than `min_cluster_points`
5. For each surviving group, compute aggregate metrics and a bounding polygon

Implementation: `backend/app/analysis/firms_clustering.py`

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `FIRMS_CLUSTER_GRID_DEG` | `0.5` | Lat/lon grid cell size in degrees (~55 km at equator) |
| `FIRMS_CLUSTER_TIME_HOURS` | `24` | Time bucket width in hours |
| `FIRMS_MIN_CLUSTER_POINTS` | `3` | Minimum detections to form a cluster |

## Cluster output (`source_metadata`)

| Field | Description |
|-------|-------------|
| `cluster_id` | Stable hash from grid cell + time bucket |
| `point_count` | Number of raw detections aggregated |
| `bounding_geometry` | GeoJSON Polygon around detections (+ 0.02° pad) |
| `centroid` | GeoJSON Point (mean lat/lon) |
| `first_detected_at` / `last_detected_at` | ISO timestamps |
| `max_confidence` / `avg_confidence_score` | From VIIRS confidence labels |
| `satellite_sources` | Unique satellite codes |
| `maximum_brightness` | Peak brightness (K) |
| `fire_radiative_power` | `{maximum, average}` FRP in MW |
| `source_record_ids` | Point IDs only — not full raw rows |

## Severity heuristic

Documented in `cluster_severity()`:

| Condition | Severity |
|-----------|----------|
| ≥20 points OR max FRP ≥500 OR max brightness ≥400 | `extreme` |
| ≥10 points OR max FRP ≥100 OR max brightness ≥330 | `severe` |
| ≥5 points OR max FRP ≥30 OR max brightness ≥300 | `moderate` |
| ≥2 points | `minor` |
| else | `unknown` |

## Limitations

- Grid clustering can split or merge fires at cell boundaries; tuning `grid_deg` trades precision vs. noise.
- Time buckets are fixed-width, not sliding windows — two detections 25h apart may land in different buckets with default 24h.
- Confidence mapping is VIIRS-specific (`low` / `nominal` / `high`).
- Clusters are **not** official fire perimeters — they indicate thermal anomaly density.
- Raw FIRMS points are **not** persisted; re-clustering requires a new ingest fetch.

## Alternatives considered

| Approach | Why not v1 |
|----------|------------|
| DBSCAN | Heavier dependency; harder to explain in demos |
| Store all points + cluster at query time | DB/LLM explosion |
| One point = one observed_event | Violates Phase 3 requirement |

## References

- [docs/firms-mapping.md](firms-mapping.md)
- [NASA FIRMS API](https://firms.modaps.eosdis.nasa.gov/api/)
