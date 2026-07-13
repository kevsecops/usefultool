# NASA EONET Natural Events Mapping

> **Source:** [NASA EONET API v3](https://eonet.gsfc.nasa.gov/docs/v3)  
> **Adapter:** `backend/app/sources/eonet.py`  
> **Record type:** `observed_event`  
> **source_id:** `eonet`

## Official Endpoints (verified live 2026-07-13)

| Endpoint | URL | Purpose |
|----------|-----|---------|
| Open events | `https://eonet.gsfc.nasa.gov/api/v3/events?status=open` | **Default ingest** — active natural events |
| Event detail | `https://eonet.gsfc.nasa.gov/api/v3/events/{id}` | Single event with full geometry history |
| Categories | `https://eonet.gsfc.nasa.gov/api/v3/categories` | Category taxonomy reference |
| Closed events | `https://eonet.gsfc.nasa.gov/api/v3/events?status=closed` | Historical; not ingested (used for deactivation logic) |

**SSRF allowlist:** `eonet.gsfc.nasa.gov` only.

**Config:** `EONET_BASE_URL` (default `https://eonet.gsfc.nasa.gov/api/v3`)

## Response Format

List response wraps events in an `events[]` array (not GeoJSON FeatureCollection):

```json
{
  "title": "EONET Events",
  "events": [{
    "id": "EONET_21233",
    "title": "Wildfire Rose Hill Bay, Duplin, North Carolina",
    "description": "2 Miles SW from Rose Hill, NC",
    "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_21233",
    "closed": null,
    "categories": [{ "id": "wildfires", "title": "Wildfires" }],
    "sources": [{ "id": "IRWIN", "url": "https://irwin.doi.gov/..." }],
    "geometry": [{
      "magnitudeValue": 525.0,
      "magnitudeUnit": "acres",
      "date": "2026-07-09T11:59:00Z",
      "type": "Point",
      "coordinates": [-78.0655556, 34.805]
    }]
  }]
}
```

Each event may have **multiple geometry snapshots** (time series). The adapter uses **only the latest snapshot** (by `date`) to avoid duplicate events per geometry version.

Supported geometry types: `Point`, `LineString`, `Polygon`, `MultiPolygon`.

## Category Mapping → Canonical

| EONET category id | Canonical `category` |
|-------------------|---------------------|
| `wildfires` | `wildfire` |
| `severeStorms` | `weather` |
| `volcanoes` | `volcano` |
| `floods` | `flood` |
| `earthquakes` | `earthquake` |
| `landslides`, `drought`, `dustHaze`, `seaLakeIce`, `waterColor` | `environmental` |
| `snow`, `tempExtremes` | `weather` |
| `manmade` | `other` |

## Field Mapping → `CanonicalObservedEvent`

| EONET field | Observed event field | Notes |
|-------------|---------------------|-------|
| `id` | `source_event_id` | e.g. `EONET_21233` |
| `link` / `sources[0].url` | `source_url` | Prefer upstream source URL |
| `title` | `title` | |
| `description` | `location_name`, `description` | |
| `categories[0].id` | `event_type` | Raw EONET category id |
| — | `category` | Mapped via table above |
| Latest geometry | `geometry`, `latitude`, `longitude` | One snapshot per event |
| Latest `geometry.date` | `issued_at`, `starts_at` | |
| `closed` | `ends_at` | When event closed |
| — | `spatial_scope` | `local` (Point), `regional` (LineString/Polygon) |
| Full event | `raw_payload` | Unmodified EONET event object |

### `source_metadata` (JSONB)

| Key | Source |
|-----|--------|
| `eonet_id` | `id` |
| `eonet_categories` | Category id list |
| `eonet_sources` | Upstream source references |
| `geometry_snapshot_count` | Length of `geometry[]` |
| `latest_geometry_date` | Date of selected snapshot |
| `magnitude_value` / `magnitude_unit` | From latest geometry (acres, kts, etc.) |
| `closed` | Closure timestamp if any |

## Severity (rule-based)

| Signal | Rule |
|--------|------|
| Storm `kts` | ≥100 extreme, ≥75 severe, ≥50 moderate, ≥34 minor |
| Wildfire `acres` | ≥100k extreme, ≥10k severe, ≥1k moderate, ≥100 minor |
| Volcano / flood | Default `moderate` when no magnitude |

## Active vs Closed Events

- Ingest fetches `status=open` only.
- Events absent from the feed are **deactivated** via `_deactivate_stale_observed_events` (same pattern as USGS).
- Closed events (`closed` timestamp set) are not re-fetched; existing rows go inactive when not in open feed.

## Fixtures

`fixtures/eonet/events_open.json`:
- Tropical storm with `LineString` track (latest geometry)
- California wildfire (`Point`)
- Chile volcano (`Point`)

## Live vs Fixture

| Modus | Bedingung |
|-------|-----------|
| Fixture | `DEMO_MODE=true` or `EONET_USE_FIXTURES=true` |
| Live | `eonet` in `SOURCES_LIVE` |
| Fallback | `EONET_FALLBACK_TO_FIXTURES=true` on fetch failure |
