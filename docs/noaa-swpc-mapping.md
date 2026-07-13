# NOAA SWPC Field Mapping

> **Adapter:** `backend/app/sources/noaa_swpc.py`  
> **Parent doc:** [space-weather.md](space-weather.md)

## Alerts Feed (`alerts.json`)

Array of text products:

```json
[{
  "product_id": "K09A",
  "issue_datetime": "2026-07-12 18:03:00.953",
  "message": "Space Weather Message Code: ALTK09\r\nSerial Number: 1042\r\n..."
}]
```

### Alert → `CanonicalObservedEvent`

| SWPC field / parsed | Observed event field | Notes |
|---------------------|---------------------|-------|
| `product_id` + serial | `source_event_id` | `swpc-alert-{product_id}-{serial}` |
| Parsed NOAA Scale | `severity` | G/S/R level → rule table |
| `message` (scale line) | `title`, `description` | Parsed `NOAA Scale: G4 - Severe` |
| Message code | `event_type` | e.g. `ALTK09` |
| — | `category` | `environmental` |
| — | `geometry` | `null` |
| Alert text | `spatial_scope`, lat bounds | Regex: poleward of N degrees |
| — | `source_metadata.potential_systems` | By scale type/level |
| — | `source_metadata.scale_documentation` | Rule-based scale docs |
| `issue_datetime` | `issued_at` | Parsed to UTC |
| Full item | `raw_payload` | |

## Scales Feed (`noaa-scales.json`)

Object keyed by day offset (`-1` = yesterday observed, `0` = current, `1`–`3` = forecast):

```json
{
  "0": {
    "DateStamp": "2026-07-13",
    "TimeStamp": "13:44:00",
    "G": { "Scale": "0", "Text": "none" },
    "S": { "Scale": "0", "Text": "none", "Prob": null },
    "R": { "Scale": "0", "Text": "none", "MinorProb": null, "MajorProb": null }
  }
}
```

### Scale entry → `CanonicalObservedEvent`

| SWPC field | Observed event field | Notes |
|------------|---------------------|-------|
| `swpc-scale-{G\|S\|R}-{day_key}` | `source_event_id` | One event per active scale per day slot |
| Scale type + level | `title` | e.g. `Geomagnetic Storm G4 (observed yesterday)` |
| `Scale` > 0 | `severity` | Rule-based G/S/R map |
| — | `geometry` | `null` |
| Scale type | `spatial_scope` | G→global, S→orbital, R→global |
| G scale | `affected_latitude_min/max` | Default 50°–90° when active |
| — | `source_metadata.day_label` | `current`, `observed_yesterday`, `forecast_day1`, etc. |
| `Prob` / `MinorProb` | `source_metadata.probability` | Forecast probability when present |
| DateStamp + TimeStamp | `issued_at` | Combined ISO UTC |

## Product ID Hints

| Prefix | Product family |
|--------|----------------|
| `K` | Geomagnetic K-index (G scale) |
| `S` | Solar radiation (S scale) |
| `R` / `ALT` | Radio blackout (R scale) |
| `EF` | Electron flux |

## Deactivation

Events not present in the latest alerts + scales fetch are deactivated (per-source stale logic). Cancel messages remain in feed until replaced.

## SSRF

Only `services.swpc.noaa.gov` and `swpc.noaa.gov` hosts allowed via `HttpClient.allowed_hosts`.
