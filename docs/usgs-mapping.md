# USGS Earthquake Feed Mapping

> **Source:** [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/)  
> **Adapter:** `backend/app/sources/usgs.py`  
> **Record type:** `observed_event` (not `alert`)

## Official Endpoints (verified live)

| Feed | URL | Use in MVP |
|------|-----|------------|
| Past day (all magnitudes) | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson` | **Default** — `USGS_BASE_URL` + `/summary/all_day.geojson` |
| Past hour | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson` | Optional higher-frequency ingest |
| Significant (month) | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson` | Showcase / filtering |
| Event detail | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{event_id}.geojson` | Future enrichment (PAGER detail) |

**SSRF allowlist:** `earthquake.usgs.gov` only (via `HttpClient.allowed_hosts`).

## Response Format

GeoJSON `FeatureCollection` with `features[]` of type `Feature`:

```json
{
  "type": "Feature",
  "id": "us7000szzy",
  "geometry": { "type": "Point", "coordinates": [lon, lat, depth_km] },
  "properties": {
    "mag": 6.4,
    "place": "191 km SE of Lorengau, Papua New Guinea",
    "time": 1783932807913,
    "updated": 1783945721040,
    "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000szzy",
    "detail": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/us7000szzy.geojson",
    "alert": "green",
    "status": "reviewed",
    "tsunami": 0,
    "sig": 630,
    "felt": null,
    "cdi": null,
    "mmi": 4.289,
    "magType": "mww",
    "type": "earthquake",
    "title": "M 6.4 - 191 km SE of Lorengau, Papua New Guinea"
  }
}
```

Timestamps `time` and `updated` are **Unix milliseconds**.

## Field Mapping → `CanonicalObservedEvent`

| USGS field | Observed event field | Notes |
|------------|---------------------|-------|
| `id` | `source_event_id` | e.g. `us7000szzy` |
| `properties.url` | `source_url` | Event page |
| `properties.title` | `title` | USGS-generated title |
| `properties.place` | `location_name` | Human-readable location |
| `properties.type` | `event_type` | Usually `earthquake` |
| — | `category` | Always `earthquake` |
| `geometry` | `geometry`, `latitude`, `longitude` | Point; depth in `source_metadata.depth_km` |
| `properties.time` | `issued_at`, `starts_at` | ms epoch → UTC |
| `properties.updated` | `updated_at_source` | ms epoch → UTC |
| `properties.status` | `status` | `automatic` / `reviewed` / `deleted` |
| — | `spatial_scope` | Default `local` |
| Full feature | `raw_payload` | Unmodified GeoJSON feature |

### `source_metadata` (JSONB)

| Key | USGS source |
|-----|-------------|
| `magnitude` | `properties.mag` |
| `mag_type` | `properties.magType` |
| `depth_km` | `geometry.coordinates[2]` |
| `alert` | `properties.alert` (PAGER: green/yellow/orange/red) |
| `significance` | `properties.sig` |
| `tsunami` | `properties.tsunami` (0/1) |
| `felt` | `properties.felt` |
| `cdi` | `properties.cdi` (DYFI) |
| `mmi` | `properties.mmi` (shakemap) |
| `net` | `properties.net` |
| `status` | `properties.status` |
| `detail_url` | `properties.detail` |

## Severity Normalization

**Not magnitude-only.** Priority order:

1. **PAGER `alert`** (if present): green → minor, yellow → moderate, orange → severe, red → extreme
2. **`significance` (`sig`)** thresholds: ≥600 extreme, ≥400 severe, ≥200 moderate, ≥40 minor
3. **Tsunami flag** bumps severity one level (capped at extreme)

## Confidence

| Rule | Value |
|------|-------|
| `status=reviewed` | `high` |
| `mag ≥ 4.0` (automatic) | `medium` |
| Otherwise | `low` |

## Fixture / Live Mode

| Env var | Default | Behavior |
|---------|---------|----------|
| `DEMO_MODE` | `false` | `true` → fixtures |
| `USGS_USE_FIXTURES` | `false` | Force fixtures |
| `USGS_FALLBACK_TO_FIXTURES` | `true` | Live failure → fixtures |
| `SOURCES_LIVE` | `nina,gdacs,noaa` | Add `usgs` for live feed |

Fixtures: `fixtures/usgs/all_day_demo.geojson` (3 events). Timestamps refreshed via `refresh_usgs_fixture()`.

## Fingerprint

Same strategy as alerts, using `source_event_id`:

```
SHA256(source | source_event_id | normalize(title) | issued_at | severity | category)
```

## Deactivation

Events not present in the latest `all_day` feed are marked `is_active=false` (stale detection per ingest cycle).
