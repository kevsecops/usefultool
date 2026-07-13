# NINA/BBK → Canonical Alert Mapping

> **Status:** Phase 7 — implemented in `backend/app/sources/nina.py`  
> **Source:** [warnung.bund.de api31](https://warnung.bund.de/api31) (official host; community docs at [nina.api.bund.dev](https://nina.api.bund.dev/))

## Endpoints

```
GET https://warnung.bund.de/api31/mowas/mapData.json
GET https://warnung.bund.de/api31/dwd/mapData.json
GET https://warnung.bund.de/api31/warnings/{identifier}.json
GET https://warnung.bund.de/api31/warnings/{identifier}.geojson
```

`mapData.json` returns a JSON array of compact alert entries. For each `id`, detail and geometry are fetched separately.

Conditional GET: responses include `ETag` and `Cache-Control: max-age=10` — the HTTP client sends `If-None-Match` on repeat requests.

## Field Mapping

| NINA Field | Canonical Field | Transform |
|------------|-----------------|-----------|
| `id` (compact) / `identifier` (detail) | `source_alert_id` | Direct |
| `i18nTitle.de` / `.en` | `title` | Prefer `de`, fallback `en` |
| `info[0].description` | `description` | HTML sanitized via `bleach` |
| `info[0].instruction` | `instruction` | HTML sanitized |
| `info[0].severity` / compact `severity` | `severity` | CAP enum via `normalize_cap_severity()` |
| `info[0].urgency` / compact `urgency` | `urgency` | Lowercase → `Urgency` enum |
| `info[0].certainty` | `certainty` | Lowercase → `Certainty` enum |
| `status` | `status` | Lowercase → `AlertStatus` enum |
| `sent` / `startDate` | `issued_at` | ISO 8601 parse |
| `info[0].effective` | `effective_at` | ISO 8601 parse |
| `info[0].onset` | `starts_at` | ISO 8601 parse |
| `info[0].expires` | `expires_at` | ISO 8601 parse |
| `transKeys.event` (BBK-EVC-*) | `event_type`, `category` | `normalize_nina_event_code()` |
| `info[0].category[]` | `category` | Fallback via `normalize_cap_category()` |
| `info[0].area[0].areaDesc` | `location_name` | Direct |
| GeoJSON geometry | `geometry`, `latitude`, `longitude` | Shapely centroid |
| — | `country_code` | Constant `DE` |
| — | `country_name` | Constant `Germany` |
| — | `language` | Constant `de` |
| — | `source_url` | `{NINA_BASE_URL}/warnings/{id}.json` |

## BBK Event Code → Category

| Event code pattern | Canonical `category` |
|--------------------|---------------------|
| `*FLOOD*`, `*FLD*` | `flood` |
| `*FIRE*`, `*WF*` | `wildfire` |
| `*WATER*`, `*HEALTH*` | `health` |
| `*STORM*`, `*WEATHER*`, `*DWD*` | `weather` |
| `*EVAC*`, `*CIVIL*`, `*MOWAS*` | `civil` |
| (no match) | `other` or CAP `category[]` fallback |

## Severity Mapping (CAP)

| NINA `severity` | Canonical `severity` |
|-----------------|---------------------|
| Unknown | `unknown` |
| Minor | `minor` |
| Moderate | `moderate` |
| Severe | `severe` |
| Extreme | `extreme` |

## Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `DEMO_MODE` | `false` | All sources use fixtures |
| `NINA_USE_FIXTURES` | `false` | Force NINA fixtures even when live |
| `NINA_FALLBACK_TO_FIXTURES` | `false` | On live fetch failure, use fixtures if available (no merge with live data) |
| `SOURCES_LIVE` | `nina,gdacs,noaa` | Comma-separated live sources when not in demo mode |
| `NINA_USER_AGENT` | `GlobalRiskIntelligence/1.0` | Sent on all NINA requests |
| `NINA_BASE_URL` | `https://warnung.bund.de/api31` | API base URL |
| `NINA_FETCH_TIMEOUT_SECONDS` | `10` | HTTP timeout (health check uses same) |
| `NINA_MAX_RETRIES` | `3` | Retry count with exponential backoff |

## Graceful Degradation

When `NINA_FALLBACK_TO_FIXTURES=true` and live fetch fails or returns zero alerts, the adapter logs a warning and loads `fixtures/nina/mapdata_*.json`. Per-alert detail/geometry fetches that fail are logged and skipped (compact entry still ingested with partial data). **Fixtures are never merged with a successful live response.**

Set `NINA_FALLBACK_TO_FIXTURES=false` (default) to avoid silent fixture injection in production.

## Deduplication

Alerts are deduplicated by `(source, source_alert_id)` unique constraint. NINA `id` values are globally unique per warning. Overlaps between MoWaS and DWD feeds for the same event are rare but handled by distinct IDs.

## Known API Quirks

- `mapData.json` returns a **JSON array**, not an object — requires `get_json_list()` in the HTTP client
- `dwd/mapData.json` may be empty seasonally — adapter continues with MoWaS data only
- Warning IDs contain dots and slashes — URL-encoded when fetching detail/geojson
- HTML in descriptions uses `<br/>` tags — sanitized before storage
- No official OpenAPI from BBK; community documentation may lag API changes
