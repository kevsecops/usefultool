# Showcase Mode

> **Phase 8** — Curated demo scenarios for presentations without external API keys.

## Overview

`SHOWCASE_MODE=true` loads three curated hazard scenarios from `fixtures/showcase/` on startup (or via CLI). All data is labeled **Showcase / Demo** in the UI and uses `ingest_mode=showcase`.

This mode is distinct from `DEMO_MODE`:

| Mode | Purpose | Data source |
|------|---------|-------------|
| `DEMO_MODE=true` | CI/offline technical fixtures | `fixtures/{source}/` |
| `SHOWCASE_MODE=true` | Stable presentation storyline | `fixtures/showcase/` |
| Live (both false) | Production ingest | External APIs |

## Scenarios

### 1. Earthquake near Port & Airport (`earthquake_port`)

- **Source:** USGS observed event
- **Location:** Southern California — M6.8 near San Pedro
- **Exposure:** Port of Los Angeles, LAX airport
- **Fixture:** `fixtures/showcase/earthquake_port/usgs.geojson`

### 2. Tropical Storm & Port Infrastructure (`tropical_storm`)

- **Sources:** GDACS alert + NASA EONET track
- **Location:** Western Mediterranean (Valencia/Barcelona)
- **Exposure:** Port of Valencia, Port of Barcelona, BCN airport
- **Fixtures:** `fixtures/showcase/tropical_storm/gdacs.json`, `eonet.json`

### 3. Geomagnetic Storm G4 (`geomagnetic_storm`)

- **Source:** NOAA SWPC space weather
- **Scale:** G4 Severe geomagnetic storm
- **Exposure:** Power plants (Gravelines, Bełchatów, Diablo Canyon)
- **Fixture:** `fixtures/showcase/geomagnetic_storm/swpc.json`

## Configuration

```bash
# .env
SHOWCASE_MODE=true
DEMO_MODE=false          # recommended: showcase replaces live ingest
SCHEDULER_ENABLED=true   # scheduler runs showcase ingest every 15 min
```

Docker Compose:

```yaml
environment:
  SHOWCASE_MODE: "true"
  DEMO_MODE: "false"
```

## Usage

### Automatic (recommended)

With `SHOWCASE_MODE=true`, the backend loads showcase data on startup if no canonical events exist. The scheduler repeats ingest on the configured interval.

```bash
docker compose up -d --build
# Showcase ingest runs immediately via STARTUP_PIPELINE_ENABLED
curl http://localhost:8000/health | jq '.showcase_mode, .canonical_event_count'
```

### Manual CLI

```bash
docker compose exec backend python -m app.jobs.cli showcase-ingest
```

### Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/events?active=true
curl http://localhost:8000/api/v1/observed-events?active=true
curl http://localhost:3000/events
```

## UI Indicators

- **Homepage:** Violet "Showcase / Demo-Modus aktiv" banner
- **Map:** "Showcase / Demo" badge + layer controls
- **Events:** Showcase label on list and detail pages
- **Briefing:** Source health panel shows `ingest_mode: showcase`
- **Map popups:** Purple "Showcase" ingest badge

## Exposure Assets

Showcase-specific exposure fixtures live in `fixtures/showcase/exposure/`:

- `ports.json` — LA, Valencia, Barcelona
- `airports.json` — LAX, BCN
- `power_plants.json` — Gravelines, Bełchatów, Diablo Canyon

After ingest, correlation links sources → canonical events, then exposure and implications are calculated automatically.

## No API Keys Required

Showcase mode uses only local fixtures. No `FIRMS_MAP_KEY`, `NOAA_USER_AGENT` live fetch, or NINA/GDACS credentials needed for the demo storyline.

## Health Endpoint

`GET /health` returns:

```json
{
  "showcase_mode": true,
  "ingest_mode": "showcase",
  "canonical_event_count": 3,
  "active_observed_event_count": 5
}
```

## Disclaimer

Showcase data is **curated for demonstration only**. It does not represent live official warnings. The standard dashboard disclaimer applies.
