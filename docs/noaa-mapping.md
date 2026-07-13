# NOAA/NWS → Canonical Alert Mapping

> **Status:** Phase 3 — implemented in `backend/app/sources/noaa.py`  
> **Source:** [NWS Alerts Web Service](https://www.weather.gov/documentation/services-web-alerts)

## Endpoint

```
GET https://api.weather.gov/alerts/active
Accept: application/geo+json
User-Agent: <required>
```

Pagination: follow `pagination.next` in the JSON body or `Link: rel="next"` header until exhausted.

Response containers: `features[]` (GeoJSON) or `@graph[]` (JSON-LD).

## Field Mapping

| NWS Field | Canonical Field | Transform |
|-----------|-----------------|-----------|
| `properties.id` | `source_alert_id` | Strip URL prefix if present |
| `properties.event` | `event_type` | Direct |
| `properties.event` | `category` | Keyword map via `normalize_event_name()` |
| `properties.headline` | `title` | Fallback: `event`, then `"NOAA Alert"` |
| `properties.description` | `description` | HTML sanitized via `bleach` |
| `properties.instruction` | `instruction` | HTML sanitized |
| `properties.severity` | `severity` | CAP enum via `normalize_cap_severity()` |
| `properties.urgency` | `urgency` | Lowercase → `Urgency` enum |
| `properties.certainty` | `certainty` | Lowercase → `Certainty` enum |
| `properties.status` | `status` | Lowercase → `AlertStatus` enum |
| `properties.sent` | `issued_at` | ISO 8601 parse |
| `properties.effective` | `effective_at` | ISO 8601 parse |
| `properties.onset` | `starts_at` | ISO 8601 parse |
| `properties.expires` | `expires_at` | ISO 8601 parse |
| `properties.sent` | `updated_at_source` | ISO 8601 parse |
| `properties.areaDesc` | `location_name` | Direct |
| `properties.areaDesc` (last segment) | `region` | Split on `,`, take last |
| `geometry` | `geometry` | GeoJSON Polygon/MultiPolygon |
| `geometry` | `latitude`, `longitude` | Shapely centroid |
| — | `country_code` | Constant `US` |
| — | `country_name` | Constant `United States` |
| — | `language` | Constant `en-US` |
| Feature `id` / `properties.@id` | `source_url` | URL or `urn:` → full NWS URL |

## Severity Mapping (CAP)

| NWS `severity` | Canonical `severity` |
|----------------|---------------------|
| Unknown | `unknown` |
| Minor | `minor` |
| Moderate | `moderate` |
| Severe | `severe` |
| Extreme | `extreme` |

## Urgency Mapping (CAP)

| NWS `urgency` | Canonical `urgency` |
|---------------|----------------------|
| Immediate | `immediate` |
| Expected | `expected` |
| Future | `future` |
| Past | `past` |

## Certainty Mapping (CAP)

| NWS `certainty` | Canonical `certainty` |
|-----------------|----------------------|
| Observed | `observed` |
| Likely | `likely` |
| Possible | `possible` |
| Unlikely | `unlikely` |

## Category Mapping (Event Name Keywords)

| Event keyword (case-insensitive) | Canonical `category` |
|----------------------------------|---------------------|
| flood | `flood` |
| tsunami | `tsunami` |
| earthquake | `earthquake` |
| volcano | `volcano` |
| wildfire, fire | `wildfire` |
| tornado, thunderstorm, hurricane, cyclone, storm, heat, wind, snow, winter, frost | `weather` |
| water, health | `health` |
| evacuation, civil | `civil` |
| (no match) | `other` |

## Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `DEMO_MODE` | `false` | All sources use fixtures |
| `NOAA_USE_FIXTURES` | `false` | Force NOAA fixtures even when live |
| `NOAA_FALLBACK_TO_FIXTURES` | `true` | On live fetch failure, use fixtures if available |
| `SOURCES_LIVE` | `noaa` | Comma-separated live sources when not in demo mode |
| `NOAA_USER_AGENT` | — | **Required** for live requests |
| `NOAA_FETCH_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `NOAA_MAX_RETRIES` | `3` | Retry count with exponential backoff |

## Graceful Degradation

When `NOAA_FALLBACK_TO_FIXTURES=true` (default) and live fetch fails (timeout, 403, 5xx), the adapter logs a warning and loads `fixtures/noaa/alerts_active_*.json`. Set `NOAA_FALLBACK_TO_FIXTURES=false` to fail hard instead.

## Deduplication

Alerts are deduplicated by `(source, source_alert_id)` unique constraint. Content changes update the existing row and regenerate the fingerprint. Alerts absent from the active feed are marked `is_active=false`.
