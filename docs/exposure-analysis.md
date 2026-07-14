# Exposure Analysis

> **Phase:** 5 — Exposure Layer & Geospatial Analysis  
> **Status:** Rule-based heuristics for demo/showcase — **not scientific damage modeling**

## Overview

Phase 5 adds a curated **exposure asset layer** (ports, airports, power plants) and computes
**event-to-asset exposures** against canonical events. Analysis is deterministic, documented,
and intended for operational awareness — not predictive hazard science.

## Demo Data

All assets in `fixtures/exposure/` are **demo fixtures for showcase purposes only**:

| File | Count | Asset type | License / source note |
|------|-------|------------|----------------------|
| `ports.json` | 12 | `port` | Publicly known major port names and approximate coordinates; not a production maritime database |
| `airports.json` | 13 | `airport` | Publicly known IATA airports with approximate WGS84 coordinates; not an aviation authority dataset |
| `power_plants.json` | 10 | `power_plant` | Well-known large facilities for demo narrative; not a complete generation asset registry |

**Do not treat these as authoritative global infrastructure inventories.** They exist to
demonstrate geospatial exposure logic in the MVP showcase.

Import via:

```bash
python -m app.jobs.cli import-exposure
```

## Data Model

### `exposure_assets`

Critical infrastructure points with PostGIS `POINT` geometry.

### `event_asset_exposures`

Links canonical events to assets with:

| Field | Values |
|-------|--------|
| `exposure_type` | `inside_event_area`, `near_event_area`, `system_level_exposure`, `unknown` |
| `distance_km` | Haversine distance for point events; `null` for polygon/system-level |
| `overlap` | `true` when asset is inside event geometry or heuristic radius |
| `confidence` | `low`, `medium`, `high` |
| `rationale` | Human-readable rule explanation |
| `analysis_version` | Currently `1` |

## Analysis Rules (v1)

Configurable buffer: `EXPOSURE_BUFFER_KM` (default **50 km**) for `near_event_area`.

### Earthquakes (USGS observed or canonical)

**Heuristic felt/damage radius** — not a ground-motion model:

```
base_radius_km = 10 × 1.8^(magnitude − 4)
depth_factor   = max(0.5, 1 − depth_km / 300)
severity_factor = {extreme: 1.5, severe: 1.2, moderate: 1.0, minor: 0.8}
effective_radius = max(5, base × depth_factor × severity_factor)
```

- `inside_event_area`: asset within `effective_radius`
- `near_event_area`: asset within `effective_radius + EXPOSURE_BUFFER_KM`

Magnitude from `source_metadata.magnitude` or parsed from title (`M6.5`).

### Fire clusters (FIRMS)

Uses cluster `bounding_geometry` from `source_metadata` (or event geometry):

- `inside_event_area`: `ST_Intersects(asset, cluster_bbox)`
- `near_event_area`: `ST_DWithin(asset, cluster_bbox, buffer_deg)`

### Storms / floods (EONET, GDACS, NOAA polygons)

- `inside_event_area`: `ST_Contains(event_polygon, asset_point)`
- `near_event_area`: `ST_DWithin(event_polygon, asset_point, buffer)`

### Space weather (NOAA SWPC)

**No point-distance matching.** Uses `system_level_exposure`:

1. Read `potential_systems` from observed event `source_metadata`
2. Map systems → asset types:
   - `power_grid` → `power_plant`
   - `satellite_operations`, `hf_radio` → `airport`, `port`
   - `gnss`, `aviation` → `airport`
3. Filter by `affected_latitude_min` when present (high-latitude G-scale events)
4. `spatial_scope` of `global` / `orbital` → broader confidence rationale

## API

| Endpoint | Method | Auth |
|----------|--------|------|
| `/api/v1/assets` | GET | Public |
| `/api/v1/assets/{id}` | GET | Public |
| `/api/v1/events/{id}/exposures` | GET | Public |
| `/api/v1/exposure/analysis?event_id=` | GET | Public |
| `/api/v1/admin/calculate-exposure` | POST | `X-Admin-Token` |

### Example curls

```bash
# List ports in Europe bbox
curl "http://localhost:8000/api/v1/assets?asset_type=port&bounding_box=0,35,15,55&limit=10"

# Exposures for a canonical event
curl "http://localhost:8000/api/v1/events/{EVENT_ID}/exposures"

# Trigger analysis (admin)
curl -X POST "http://localhost:8000/api/v1/admin/calculate-exposure" \
  -H "X-Admin-Token: dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"active_only": true}'
```

## CLI

```bash
python -m app.jobs.cli import-exposure
python -m app.jobs.cli calculate-exposure
python -m app.jobs.cli calculate-exposure --event-id <UUID>
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPOSURE_BUFFER_KM` | `50` | Buffer for `near_event_area` |
| `EXPOSURE_AUTO_RUN` | `false` | Run exposure calc after correlation/ingest |

## Limitations

1. **Heuristic radii** for earthquakes — not USGS ShakeMap or PAGER exposure
2. **Demo assets only** — incomplete global coverage by design
3. **No Implications Engine** (Phase 6) — exposures are facts, not business impact scores
4. **No frontend map layers** (Phase 8) — API/CLI only in this phase
5. Polygon buffers use degree approximation (`km / 111.32`) — adequate for MVP demo scale
6. Space weather matching is system-type relevance, not geomagnetic field modeling

## Analysis Version

Current: **`1`**. Bump when rules change; stored per `event_asset_exposures` row.
