# NOAA Space Weather (SWPC)

> **Source:** [NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov/)  
> **Adapter:** `backend/app/sources/noaa_swpc.py`  
> **Record type:** `observed_event`  
> **source_id:** `noaa_swpc` (separate from `noaa` NWS weather alerts)

## Overview

NOAA SWPC publishes space weather conditions affecting satellites, power grids, GNSS, HF radio, and aviation. Unlike NWS CAP alerts, many SWPC events are **global or zonal** without point geometry.

The adapter ingests two official JSON feeds:

| Feed | URL | Content |
|------|-----|---------|
| **NOAA Scales** | `https://services.swpc.noaa.gov/products/noaa-scales.json` | Current and forecast G/S/R scale levels |
| **SWPC Alerts** | `https://services.swpc.noaa.gov/products/alerts.json` | Active watches, warnings, alerts (text products) |

Both endpoints verified live **2026-07-13** (HTTP 200).

**SSRF allowlist:** `services.swpc.noaa.gov`, `swpc.noaa.gov`

**Config:** `NOAA_SWPC_BASE_URL` (default `https://services.swpc.noaa.gov/products`)

## NOAA Space Weather Scales (G / S / R)

Transparent mapping to canonical `severity` (rule-based, documented in `source_metadata.scale_documentation`):

### G — Geomagnetic Storm

| Level | Label | Canonical severity | Typical impacts |
|-------|-------|-------------------|-----------------|
| G1 | Minor | `minor` | Weak power grid fluctuations, aurora high latitudes |
| G2 | Moderate | `moderate` | HF radio fading, voltage alarms at high latitudes |
| G3 | Strong | `severe` | Satellite anomalies, intermittent navigation issues |
| G4 | Severe | `severe` | Widespread voltage problems, satellite surface charging |
| G5 | Extreme | `extreme` | Grid collapse risk, complete HF blackout on sunlit side |

**Spatial scope:** `global` with `affected_latitude_min`/`max` (e.g. poleward of 50°–60° geomagnetic latitude).

**Potential systems:** `power_grid`, `satellite_operations`, `gnss`, `hf_radio`, `aviation`

### S — Solar Radiation Storm

| Level | Label | Canonical severity |
|-------|-------|-------------------|
| S1–S5 | Minor → Extreme | `minor` → `extreme` |

**Spatial scope:** `orbital` (magnetosphere / satellite operations).

**Potential systems:** `satellite_operations`, `aviation`, `gnss`, `hf_radio`

### R — Radio Blackout

| Level | Label | Canonical severity |
|-------|-------|-------------------|
| R1–R5 | Minor → Extreme | `minor` → `extreme` |

**Spatial scope:** `global` (sunlit hemisphere).

**Potential systems:** `hf_radio`, `gnss`, `satellite_operations`, `aviation`

Scale reference: [NOAA Scales Explanation](https://www.swpc.noaa.gov/noaa-scales-explanation)

## Spatial Model

SWPC events use extended spatial fields instead of point geometry:

| Field | Usage |
|-------|-------|
| `spatial_scope` | `global`, `continental`, `regional`, `local`, `orbital` |
| `geometry` | `null` (no point geometry for most SWPC products) |
| `affected_latitude_min` / `max` | High-latitude bands from alert text (e.g. poleward of 50°) |
| `source_metadata.affected_regions` | e.g. `high_latitude`, `dayside_hemisphere`, `magnetosphere` |
| `source_metadata.potential_systems` | e.g. `satellite_operations`, `power_grid`, `gnss`, `hf_radio` |

## API

- `GET /api/v1/observed-events?source=noaa_swpc` — all SWPC observed events
- `GET /api/v1/space-weather` — convenience filter for `noaa_swpc` source

## Fixtures

`fixtures/noaa_swpc/conditions.json`:
- G4 geomagnetic storm alert (K09A)
- R2 radio blackout alert
- NOAA scales with G4 observed, G3 current, G2 forecast

## Polling Recommendation

| Feed | Interval | Notes |
|------|----------|-------|
| SWPC alerts | 5–15 min | Conditions change during active storms |
| NOAA scales | 15–30 min | Daily/forecast entries; lower churn than NWS |

See [docs/data-sources.md](data-sources.md) for global ingest intervals.

## Live vs Fixture

| Modus | Bedingung |
|-------|-----------|
| Fixture | `DEMO_MODE=true` or `NOAA_SWPC_USE_FIXTURES=true` |
| Live | `noaa_swpc` in `SOURCES_LIVE` |
| Fallback | `NOAA_SWPC_FALLBACK_TO_FIXTURES=true` on fetch failure |

## Related

- Field-level mapping: [docs/noaa-swpc-mapping.md](noaa-swpc-mapping.md)
- NWS weather alerts (separate): [docs/noaa-mapping.md](noaa-mapping.md)
