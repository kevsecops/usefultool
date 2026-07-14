# Global Risk Intelligence MVP

> **Status: Phase 8 — Showcase Mode & Dashboard Extensions**  
> PostgreSQL/PostGIS, Live ingest from **NINA (DE), GDACS (international), NOAA (US)** when `DEMO_MODE=false`, Fixture-Ingest (`DEMO_MODE=true`), Basis-API mit `bounding_box`-Filter, **Next.js Dashboard mit MapLibre GL JS**, regelbasierter Global Risk Briefing (**LLM deaktiviert by default**).

## Produktbeschreibung

**Global Risk Intelligence** aggregiert öffentliche Warnmeldungen aus nationalen und internationalen Systemen, normalisiert sie in ein einheitliches Datenmodell und stellt sie über ein read-only Dashboard dar — inklusive regelbasierter Risikoanalyse und optionalem LLM-gestütztem Global Risk Briefing. **LLM ist standardmäßig deaktiviert** (`LLM_ENABLED=false`); Briefings nutzen dann ausschließlich die regelbasierte Engine.

**Abgedeckte Gefahren (MVP):** Hochwasser, Unwetter, Waldbrände, Erdbeben, Vulkane, tropische Stürme, Tsunamis, Bevölkerungsschutz, Gesundheitswarnungen.

**Disclaimer:** Das System liefert keine amtlichen Warnungen und keine wissenschaftlich gesicherten Vorhersagen. Es aggregiert und interpretiert transparent öffentlich zugängliche Meldungen.

## Datenquellen (MVP)

| Quelle | Abdeckung | API-Basis |
|--------|-----------|-----------|
| NINA/BBK (MoWaS + DWD) | Deutschland | `https://warnung.bund.de/api31` |
| GDACS | International (Naturgefahren) | `https://www.gdacs.org/gdacsapi` |
| NOAA/NWS (full USA) | USA | `https://api.weather.gov/alerts/active` |
| USGS Earthquakes | Global (observed events) | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson` |
| NASA EONET | Global (natural events) | `https://eonet.gsfc.nasa.gov/api/v3/events?status=open` |
| NOAA SWPC | Global (space weather) | `https://services.swpc.noaa.gov/products/` |
| NASA FIRMS | Regional fire clusters (VIIRS) | `https://firms.modaps.eosdis.nasa.gov/api/area/csv/` |

**Showcase Phase 1:** USGS-Erdbeben werden als `observed_events` ingestiert (separat von `alerts`). API: `GET /api/v1/observed-events`. Siehe [docs/usgs-mapping.md](docs/usgs-mapping.md).

**Showcase Phase 2:** NASA EONET (Waldbrand, Sturm, Vulkan, …) und NOAA SWPC (G/S/R-Raumwetter) als `observed_events`. API: `GET /api/v1/observed-events`, `GET /api/v1/space-weather`. Siehe [docs/eonet-mapping.md](docs/eonet-mapping.md), [docs/space-weather.md](docs/space-weather.md).

**Showcase Phase 3:** NASA FIRMS thermal anomalies werden **während Ingest geclustert** — nur Aggregat-Cluster als `observed_events` (`active_fire_cluster`), nie einzelne Punkte. API: `GET /api/v1/fire-clusters`. Siehe [docs/firms-mapping.md](docs/firms-mapping.md), [docs/fire-clustering.md](docs/fire-clustering.md).

**Showcase Phase 7:** LLM Evidence Package — erweiterte Briefings mit Observed Events, Verified Exposure, Evidence Gaps (`LLM_ENABLED=false` by default). Siehe [docs/llm-analysis.md](docs/llm-analysis.md).

**Showcase Phase 8:** `SHOWCASE_MODE` — kuratierte Demoszenarien, Multi-Layer-Karte, Event-Detail, Dashboard-Erweiterungen. Siehe [docs/showcase.md](docs/showcase.md).

Details: [docs/data-sources.md](docs/data-sources.md)

## Architekturübersicht

```
Externe Warnquellen → Source Adapters → Normalization → PostgreSQL/PostGIS
    → Rule-based Analysis → LLM Cross-Alert Analysis → Read-only API → Dashboard (Phase 4)
                                    ↓ (Fallback)
                              Rule-based Briefing
```

Vollständiges Diagramm: [docs/architecture.md](docs/architecture.md)

## Tech Stack

| Komponente | Technologie |
|------------|-------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic |
| Datenbank | PostgreSQL 16 + PostGIS |
| Frontend (Phase 4) | Next.js, TypeScript, Tailwind CSS, **MapLibre GL JS** |
| LLM | OpenAI-kompatibel (Prod), Mock (Demo) — **Kern-Analyseschicht** |
| Deployment | Docker Compose |

## Schnellstart (Docker — empfohlen)

**Voraussetzungen:** [Docker](https://docs.docker.com/get-docker/) und Docker Compose (kein lokales Node/Python nötig).

```bash
cp .env.example .env
docker compose up -d --build
# oder: make up   bzw.   ./scripts/docker-up.sh

# Prüfen (Ingest + Briefing starten automatisch nach ~30s)
curl http://localhost:8000/health
curl http://localhost:3000
```

Der Backend-Scheduler führt **automatisch** alle 15 Minuten Ingest aus und erzeugt danach ein Briefing (`SCHEDULER_ENABLED=true`, `AUTO_GENERATE_BRIEFING=true` in `docker-compose.yml`). Kein manuelles `python -m app.jobs.cli ingest` nötig.

**Debugging (optional):**

```bash
docker compose exec backend python -m app.jobs.cli ingest
docker compose exec backend python -m app.jobs.cli generate-briefing --type auto
```

| Dienst | URL |
|--------|-----|
| **Dashboard** | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

Migrationen laufen beim Backend-Start automatisch (`docker-entrypoint.sh`). Postgres, Backend und Frontend haben Healthchecks; das Frontend startet erst, wenn die API healthy ist.

**Nach Code-Änderungen:** `docker compose up -d --build` oder `make rebuild` (vollständiger No-Cache-Rebuild).

**Logs:** `docker compose logs -f frontend backend` oder `make logs`.

**API-URLs in Containern:** Der Browser nutzt `NEXT_PUBLIC_API_URL=http://localhost:8000`. Server Components und SSR im Next.js-Container nutzen `API_URL=http://backend:8000` (siehe `frontend/lib/api.ts`).

```bash
# Live ingest — alle drei Quellen (.env: DEMO_MODE=false, NOAA_USER_AGENT + NINA_USER_AGENT setzen)
DEMO_MODE=false docker compose exec backend python -m app.jobs.cli ingest

# Einzelne Quelle
DEMO_MODE=false docker compose exec backend python -m app.jobs.cli ingest --sources nina
DEMO_MODE=false docker compose exec backend python -m app.jobs.cli ingest --sources gdacs
DEMO_MODE=false docker compose exec backend python -m app.jobs.cli ingest --sources noaa

curl http://localhost:8000/api/v1/alerts
curl "http://localhost:8000/api/v1/alerts?bounding_box=-98,32,-96,34&country=US"
curl "http://localhost:8000/api/v1/alerts?country=DE"
```

### Showcase-Modus (Demo ohne API-Keys)

```bash
# .env: SHOWCASE_MODE=true
SHOWCASE_MODE=true docker compose up -d --build

# Manuell laden
docker compose exec backend python -m app.jobs.cli showcase-ingest

curl http://localhost:8000/health   # showcase_mode: true
open http://localhost:3000/events
```

Siehe [docs/showcase.md](docs/showcase.md) für die drei kuratierten Szenarien.

### Makefile-Hilfen

| Target | Aktion |
|--------|--------|
| `make up` | `.env` anlegen falls fehlend, `docker compose up -d --build` |
| `make ingest` | Demo-Fixture-Ingest im Backend-Container |
| `make logs` | Frontend- und Backend-Logs folgen |
| `make rebuild` | `down`, `build --no-cache`, `up -d` |
| `make health` | Kurztest API + Frontend |
| `make test-backend` | `pytest` im Backend-Container |

## Entwicklung ohne Docker

### Frontend (npm)

```bash
cd frontend
npm install
cp ../.env.example ../.env   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Dashboard: http://localhost:3000 (Backend muss auf Port 8000 laufen).

Production-Build lokal (standalone — nicht `next start` verwenden):

```bash
cd frontend
rm -rf .next
npm run build
npm run start   # node .next/standalone/server.js
```

### Backend + DB (venv)

```bash
# PostgreSQL muss laufen (z. B. nur DB-Container)
docker compose up -d postgres

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
alembic upgrade head
uvicorn app.main:app --reload

# Demo-Ingest
DEMO_MODE=true python -m app.jobs.cli ingest

# Live ingest (requires NOAA_USER_AGENT, NINA_USER_AGENT)
DEMO_MODE=false SOURCES_LIVE=nina,gdacs,noaa python -m app.jobs.cli ingest
```

## Tests

```bash
# Empfohlen: voller Stack in Docker, dann Tests im Backend-Container
docker compose up -d
make test-backend
# bzw. docker compose exec backend pytest -v

# Nur mit lokaler PostgreSQL-Instanz
cd backend && pytest -v
```

## Environment-Variablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/usefultool` | PostgreSQL Connection String |
| `DEMO_MODE` | `false` | Fixtures statt Live-APIs |
| `ADMIN_TOKEN` | — | Token für Admin-Endpunkte (`X-Admin-Token`) |
| `LLM_ENABLED` | `false` | `true` aktiviert LLM-Briefings (Provider konfigurieren) |
| `LLM_PROVIDER` | `mock` | `mock`, `openai_compat`, `ollama` |
| `LLM_BASE_URL` | — | OpenAI-kompatibler Endpoint (z. B. `https://api.openai.com/v1`) |
| `LLM_API_KEY` | — | API-Key (nur Backend) |
| `LLM_MODEL` | `gpt-4o-mini` | Modellname (z. B. `gpt-4o-mini`, `llama3`) |
| `LLM_TIMEOUT_SECONDS` | `30` | LLM Request-Timeout |
| `LLM_MAX_TOKENS` | `2048` | Max. LLM-Antwortlänge |
| `LLM_MAX_EVENTS` | `20` | Max. kanonische Ereignisse im Evidence Package |
| `LLM_MAX_EXPOSURES_PER_EVENT` | `10` | Max. Asset-Exposures pro Ereignis im LLM-Input |
| `FRONTEND_URL` | `http://localhost:3000` | CORS-Origin |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend API base URL (browser) |
| `API_URL` | `http://backend:8000` | Server-side API URL (Docker) |
| `NOAA_USER_AGENT` | `GlobalRiskIntelligence/1.0` | Pflicht-Header für NOAA live |
| `NOAA_BASE_URL` | `https://api.weather.gov` | NOAA API base URL |
| `NOAA_FETCH_TIMEOUT_SECONDS` | `30` | HTTP timeout für NOAA |
| `NOAA_USE_FIXTURES` | `false` | NOAA-Fixtures erzwingen |
| `NOAA_FALLBACK_TO_FIXTURES` | `true` | Bei Live-Fehler auf Fixtures zurückfallen |
| `SOURCES_LIVE` | `nina,gdacs,noaa` | Komma-separierte Live-Quellen |
| `NINA_USER_AGENT` | `GlobalRiskIntelligence/1.0` | User-Agent für NINA live |
| `NINA_BASE_URL` | `https://warnung.bund.de/api31` | NINA API base URL |
| `NINA_USE_FIXTURES` | `false` | NINA-Fixtures erzwingen |
| `NINA_FALLBACK_TO_FIXTURES` | `false` | Bei Live-Fehler auf NINA-Fixtures zurückfallen |
| `GDACS_BASE_URL` | `https://www.gdacs.org` | GDACS API base URL |
| `GDACS_USE_FIXTURES` | `false` | GDACS-Fixtures erzwingen |
| `GDACS_FALLBACK_TO_FIXTURES` | `true` | Bei Live-Fehler auf GDACS-Fixtures zurückfallen |
| `SCHEDULER_ENABLED` | `false` | Hintergrund-Ingest im Backend-Container aktivieren |
| `INGEST_INTERVAL_MINUTES` | `15` | Intervall für automatischen Ingest (wenn Scheduler aktiv) |
| `SCHEDULER_GENERATE_BRIEFING` | `true` | Briefing nach jedem geplanten Ingest neu generieren |
| `SCHEDULER_STARTUP_DELAY_SECONDS` | `30` | Wartezeit nach Container-Start bis erster Ingest |
| `LOG_LEVEL` | `INFO` | Log-Level |
| `LOG_FORMAT` | `json` | `json` (structured) oder `text` (lesbar) |

Vollständige Liste: [.env.example](.env.example)

## Automatischer Daten-Refresh

**Standard in Docker Compose:** Der eingebaute Backend-Scheduler (`SCHEDULER_ENABLED=true`) führt alle 15 Minuten Ingest und Briefing aus. **n8n ist nicht erforderlich**, wenn der Scheduler aktiv ist — siehe [docs/n8n-integration.md](docs/n8n-integration.md).

| Methode | Wann nutzen |
|---------|-------------|
| **Backend-Scheduler** (`SCHEDULER_ENABLED=true`) | **MVP-Standard** — Container-Deployment ohne externe Tools |
| **cron / systemd timer** | Host mit Docker Compose, Scheduler deaktiviert |
| **n8n** (optional) | Externe Orchestrierung, Benachrichtigungen, Custom-Workflows |

### Eingebauter Scheduler (Docker)

```env
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
```

Der Scheduler startet im Backend-Container mit Uvicorn, führt nach 30s Startup-Delay den ersten Ingest aus und wiederholt alle `INGEST_INTERVAL_MINUTES` Minuten. Empfohlene Mindestintervalle pro Quelle: [docs/data-sources.md](docs/data-sources.md#ingest-polling-empfehlung-phase-7).

Manuell (weiterhin möglich):

```bash
docker compose exec backend python -m app.jobs.cli ingest
docker compose exec backend python -m app.jobs.cli generate-briefing --type auto
```

## Demo-Modus

`DEMO_MODE=true` aktiviert Fixture-basierte Daten aus `fixtures/` — funktioniert offline, ohne externe APIs.

**Docker Compose setzt `DEMO_MODE=false` standardmäßig** für Live-Daten (NINA, GDACS, NOAA). Fixture-Alerts aus früheren Demo-Ingests werden beim Backend-Start und vor jedem Live-Ingest deaktiviert und aus der öffentlichen API ausgeblendet.

Für **offline Demo**:

```env
DEMO_MODE=true
```

Für **echte Live-Daten**:

```env
DEMO_MODE=false
NINA_FALLBACK_TO_FIXTURES=false
SOURCES_LIVE=nina,gdacs,noaa
```

Dann `docker compose up -d --build`. Die Karte und das Dashboard zeigen nur Live-Warnungen; Demo-Fixtures erhalten ein **Demo**-Badge, wenn `DEMO_MODE=true`.

`GET /api/v1/sources` zeigt `ingest_mode` (`fixture` / `live`) pro Quelle.

### Monitoring

| Endpoint | Beschreibung |
|----------|--------------|
| `GET /health` | Öffentlich — Scheduler-Status, letzter Ingest, Alert-Zähler, `demo_mode` |
| `GET /api/v1/admin/status` | Admin-Token — Ingest-Historie, Quellen-Fehler, Scheduler-Details |

```bash
curl http://localhost:8000/health
curl -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:8000/api/v1/admin/status
```

### LLM aktivieren (optional)

```env
LLM_ENABLED=true
LLM_PROVIDER=mock   # oder openai_compat / ollama
```

### Ollama (optional, außerhalb Compose)

```bash
ollama pull llama3 && ollama serve
```

In `.env`:

```env
LLM_ENABLED=true
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3
```

```bash
docker compose exec backend python -m app.jobs.cli generate-briefing --type llm
```

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [docs/phase1-plan.md](docs/phase1-plan.md) | Konsolidierter Plan |
| [docs/architecture.md](docs/architecture.md) | Architektur & Module |
| [docs/data-model.md](docs/data-model.md) | Kanonisches Alert-Modell |
| [docs/data-sources.md](docs/data-sources.md) | API-Endpunkte & Mapping |
| [docs/noaa-mapping.md](docs/noaa-mapping.md) | NOAA/NWS → kanonisches Mapping |
| [docs/nina-mapping.md](docs/nina-mapping.md) | NINA/BBK → kanonisches Mapping |
| [docs/gdacs-mapping.md](docs/gdacs-mapping.md) | GDACS → kanonisches Mapping |
| [docs/deployment.md](docs/deployment.md) | Docker Compose Deployment |
| [docs/n8n-integration.md](docs/n8n-integration.md) | Optionale n8n-Integration |
| [docs/consistency-audit.md](docs/consistency-audit.md) | Plattform-Konsistenz-Audit |
| [docs/phase0-assessment.md](docs/phase0-assessment.md) | Phase 0 Repository Assessment (Showcase-Erweiterung) |
| [docs/llm-analysis.md](docs/llm-analysis.md) | LLM als Kern-Analyseschicht |
| [docs/risk-scoring.md](docs/risk-scoring.md) | Risk-Score-Algorithmus |
| [docs/security.md](docs/security.md) | Threat Model & Maßnahmen |

## Roadmap

| Phase | Inhalt | Status |
|-------|--------|--------|
| 1 | Planung & Dokumentation | ✅ |
| 2 | Backend, PostgreSQL/PostGIS, Fixtures, Basis-API | ✅ |
| 3 | Live NOAA source, bounding_box filter | ✅ |
| 4 | Dashboard (MapLibre GL JS) | ✅ |
| 5 | Regelbasierte Analyse & Fallback-Briefing | ✅ |
| 6 | LLM Cross-Alert-Integration | ✅ |
| 7 | Live NINA & GDACS, Deployment Hardening | ✅ |

## Lizenz

TBD
