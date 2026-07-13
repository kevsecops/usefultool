# GDACS → Canonical Alert Mapping

> **Status:** Phase 7 — implemented in `backend/app/sources/gdacs.py`  
> **Source:** [GDACS API](https://www.gdacs.org/gdacsapi/swagger/index.html)

## Endpoint

```
GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/events4app
Accept: application/geo+json, application/json
```

Returns a GeoJSON `FeatureCollection` with up to ~100 events from the last 4 days.

Optional filtered search (not used in MVP default ingest):

```
GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ&limit=10
```

## Field Mapping

| GDACS Field | Canonical Field | Transform |
|-------------|-----------------|-----------|
| `{eventtype}-{eventid}-{episodeid}` | `source_alert_id` | Composite key |
| `name` | `title` | Direct |
| `description` / `htmldescription` | `description` | HTML sanitized |
| `alertlevel` + `alertscore` | `severity` | `normalize_gdacs_alert_level()` |
| `eventtype` | `category`, `event_type` | `normalize_gdacs_event_type()` |
| `fromdate` | `issued_at`, `starts_at` | ISO 8601 parse |
| `todate` | `expires_at` | ISO 8601 parse |
| `datemodified` | `updated_at_source` | ISO 8601 parse |
| `geometry` (Point) | `geometry`, `latitude`, `longitude` | GeoJSON Point coords |
| `iso3` | `country_code` | ISO3 → ISO2 lookup table |
| `country` | `country_name`, `location_name` | Direct |
| `url.details` / `url.report` | `source_url` | Direct |
| `iscurrent` | `status` | `"true"` → `actual`, else `unknown` |
| — | `language` | Constant `en` |

## Event Type → Category

| GDACS `eventtype` | Canonical `category` |
|-------------------|---------------------|
| EQ | `earthquake` |
| TC | `weather` |
| FL | `flood` |
| VO | `volcano` |
| WF | `wildfire` |
| DR | `environmental` |
| TS | `tsunami` |
| (other) | `other` |

## Alert Level → Severity

| GDACS `alertlevel` | Canonical `severity` | Notes |
|--------------------|----------------------|-------|
| Green | `minor` | |
| Orange | `moderate` | `severe` if `alertscore >= 2` |
| Red | `severe` | `extreme` if `alertscore >= 3` |

## Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `DEMO_MODE` | `false` | All sources use fixtures |
| `GDACS_USE_FIXTURES` | `false` | Force GDACS fixtures even when live |
| `GDACS_FALLBACK_TO_FIXTURES` | `true` | On live fetch failure, use fixtures |
| `SOURCES_LIVE` | `nina,gdacs,noaa` | Comma-separated live sources |
| `GDACS_BASE_URL` | `https://www.gdacs.org` | API base URL |
| `GDACS_FETCH_TIMEOUT_SECONDS` | `15` | HTTP timeout |
| `GDACS_MAX_RETRIES` | `3` | Retry count |

## Graceful Degradation

When `GDACS_FALLBACK_TO_FIXTURES=true` (default) and live fetch fails, the adapter loads `fixtures/gdacs/events4app.json`.

## Filtering

Events with `iscurrent=false` are excluded from ingest. GDACS SEARCH results may include stale events — the adapter filters them client-side.

## Known API Quirks

- `iscurrent` is a string (`"true"` / `"false"`), not a boolean
- `alertlevel` is GDACS-specific (Green/Orange/Red), not CAP severity
- 100-event limit on `events4app` — sufficient for MVP polling every 5 minutes
- Geometry is typically a Point; polygon detail requires separate `getgeometry` endpoint (not fetched in MVP)
- `iso3` codes need manual ISO2 mapping for some countries (e.g. `PNG` → `PG`)
