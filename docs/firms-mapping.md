# NASA FIRMS — Field Mapping

> **Source ID:** `firms`  
> **Record type:** `observed_event`  
> **Event type:** `active_fire_cluster`  
> **Category:** `wildfire`

## API

| Item | Value |
|------|-------|
| Base URL | `https://firms.modaps.eosdis.nasa.gov` |
| Area endpoint | `/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}` |
| MAP_KEY | Free registration at [firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/) |
| Health check | `/api/map_key/{MAP_KEY}` |

### Default product & region

| Setting | Default | Rationale |
|---------|---------|-----------|
| `FIRMS_PRODUCT` | `VIIRS_SNPP_NRT` | Near-real-time VIIRS SNPP — good latency for showcase |
| `FIRMS_AREA_COORDS` | `0,36,20,46` | Southern Europe / Mediterranean bbox (west,south,east,north) |
| `FIRMS_DAY_RANGE` | `1` | Last 24h — balances freshness vs. API volume |
| `FIRMS_REGION_LABEL` | `Southern Europe / Mediterranean` | Human-readable region on clusters |

To query another area, set `FIRMS_AREA_COORDS` (e.g. `world` or `54,5.5,102,40` for South Asia).

## Ingest flow

```
FIRMS CSV → parse points (in-memory) → cluster → observed_events (clusters only)
```

Admin metrics per ingest:

- `raw_points_fetched` — CSV rows parsed
- `clusters_persisted` — observed events upserted

## CSV → point fields

| FIRMS column | Internal | Notes |
|--------------|----------|-------|
| `latitude` / `longitude` | `FirmsPoint.latitude/longitude` | Required |
| `acq_date` + `acq_time` | `acquired_at` | UTC datetime |
| `brightness` | `brightness` | Kelvin |
| `frp` | `frp` | Fire Radiative Power (MW) |
| `confidence` | `confidence` | `low`, `nominal`, `high` |
| `satellite` | `satellite` | e.g. `N`, `1` |
| `instrument` | `instrument` | e.g. `VIIRS` |

Point ID: `firms-{lat}-{lon}-{acq_date}-{acq_time}-{satellite}`

## Cluster → observed_event

| Cluster field | `observed_event` column |
|---------------|-------------------------|
| `cluster_id` | `source_event_id` |
| `active_fire_cluster` | `event_type` |
| `wildfire` | `category` |
| `cluster_severity()` | `severity` |
| `bounding_geometry` | `geometry` / `geometry_json` |
| centroid | `latitude`, `longitude` |
| `first_detected_at` | `issued_at`, `starts_at` |
| `last_detected_at` | `ends_at`, `updated_at_source` |
| full metadata | `source_metadata` |
| summary only | `raw_payload` (cluster_id, point_count, _ingest_mode) |

**Critical:** `raw_payload` does **not** contain individual FIRMS rows.

## Fixtures

`fixtures/firms/mediterranean_points.json` — 15 points forming 3 clusters (Spain, Greece, Portugal).

`DEMO_MODE=true` or `FIRMS_USE_FIXTURES=true` uses fixtures without `FIRMS_MAP_KEY`.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/fire-clusters` | FIRMS `active_fire_cluster` events |
| `GET /api/v1/observed-events?source=firms` | Same data, generic filter |
| `GET /health` | `observed_event_counts.firms` |
| `GET /api/v1/admin/status` | `extra_metrics.raw_points_fetched` per source |

## Example curls

```bash
# Ingest FIRMS only (fixtures in demo mode)
docker compose exec backend python -m app.jobs.cli ingest --sources firms

# List fire clusters
curl "http://localhost:8000/api/v1/fire-clusters"

# Filter by severity
curl "http://localhost:8000/api/v1/fire-clusters?severity=moderate"

# Admin metrics
curl -H "X-Admin-Token: dev-admin-token" http://localhost:8000/api/v1/admin/status
```

## Live setup

```bash
# .env — never commit MAP_KEY
FIRMS_MAP_KEY=your-key-from-nasa-email
FIRMS_USE_FIXTURES=false
SOURCES_LIVE=nina,gdacs,noaa,firms
```

See also: [docs/fire-clustering.md](fire-clustering.md), [docs/data-sources.md](data-sources.md)
