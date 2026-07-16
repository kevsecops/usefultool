# Global Risk Intelligence MVP

> **Status: Phase 9 — Hardening complete**  
> PostgreSQL/PostGIS, Live ingest from **NINA (DE), GDACS (international), NOAA (US)** when `DEMO_MODE=false`, Fixture-Ingest (`DEMO_MODE=true`), Basis-API mit `bounding_box`-Filter, **Next.js Dashboard mit MapLibre GL JS**, regelbasierter Global Risk Briefing (**LLM deaktiviert by default**), **SHOWCASE_MODE**, per-source scheduler, data retention, CI.

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

**Phase 9:** Per-source scheduler, data retention, security headers, CI workflow. Siehe [docs/deployment.md](docs/deployment.md), [docs/security.md](docs/security.md).

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

### Production / Demo (`make up`)

```bash
cp .env.example .env
make up
# oder: docker compose up -d --build

curl http://localhost:8000/health
curl http://localhost:3000
```

Beim Backend-Start läuft automatisch:

1. **Migrationen** (`docker-entrypoint.sh` → `alembic upgrade head`)
2. **Retention cleanup** — alte inaktive Alerts/Events löschen (wenn aktiviert)
3. **Startup-Pipeline** (`STARTUP_PIPELINE_ENABLED=true`): abgelaufene/Fixture-Alerts deaktivieren, optional Exposure-Fixtures importieren, dann Ingest + Analyse
4. **Per-Source-Scheduler** (`SCHEDULER_ENABLED=true`): jede Quelle in `SOURCES_LIVE` auf eigenem Intervall; Briefing separat alle `INGEST_INTERVAL_MINUTES`

Kein manuelles `python -m app.jobs.cli ingest` nötig — weder für Dev noch für Production-Deployments mit Docker Compose.

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

**Logs:** `docker compose logs -f frontend backend` oder `make logs`.

### Entwicklung mit Auto-Reload (`make dev`)

Für lokale Entwicklung **kein manuelles Rebuild** nach Code-Änderungen nötig:

```bash
cp .env.example .env   # falls noch nicht vorhanden
make dev
# oder im Vordergrund mit Compose Watch:
make dev-watch
```

| | `make dev` | `make up` |
|---|------------|-----------|
| Compose files | `docker-compose.yml` + `docker-compose.dev.yml` | `docker-compose.yml` only |
| Backend | Uvicorn `--reload` | Production image |
| Frontend | Next.js dev server (hot reload) | Standalone production build |
| Use case | Daily coding | Demo deploy, production-like test |

| Was | Verhalten |
|-----|-----------|
| Python (`backend/app/`) | Uvicorn `--reload` — Neustart bei `.py`-Änderungen |
| Frontend (TSX/CSS/…) | Next.js Dev Server (`npm run dev`) — Hot Reload |
| Postgres | unverändert (Daten bleiben im Volume) |

**Einmalig starten, dann weiter coden** — Änderungen an Anwendungscode werden automatisch übernommen.

**Rebuild nötig bei:**

- `backend/pyproject.toml` / neue Python-Dependencies → `make dev` (baut Backend neu)
- `frontend/package.json` / neue npm-Pakete → `make dev` (baut Frontend neu)
- `backend/Dockerfile` oder `frontend/Dockerfile*` geändert → `make dev`
- Neue Alembic-Migrationen → `docker compose -f docker-compose.yml -f docker-compose.dev.yml restart backend` (Migrationen laufen beim Start)

**Production / Demo-Deploy** (kein Hot Reload): `docker compose up -d --build` oder `make up` / `make rebuild`.

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
SHOWCASE_MODE=true make up

# Manuell laden
docker compose exec backend python -m app.jobs.cli showcase-ingest

curl http://localhost:8000/health   # showcase_mode: true
open http://localhost:3000/events
open http://localhost:3000/showcase
```

Kuratierte Szenarien: Erdbeben/Port, Geomagnetic Storm, Exposure-Overlay. Siehe [docs/showcase.md](docs/showcase.md).

### Makefile-Hilfen

| Target | Aktion |
|--------|--------|
| `make dev` | Dev-Stack mit Hot Reload (`docker-compose.dev.yml`), detached |
| `make dev-watch` | Wie `make dev`, Vordergrund + Compose Watch (sync/rebuild) |
| `make dev-logs` | Logs im Dev-Stack folgen |
| `make dev-down` | Dev-Stack stoppen |
| `make up` | Production-Stack: `.env` anlegen falls fehlend, `docker compose up -d --build` |
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
| `STARTUP_PIPELINE_ENABLED` | `true` | Einmalige Daten-Pipeline beim Container-Start |
| `INGEST_INTERVAL_MINUTES` | `15` | Fallback-Intervall + Briefing-Scheduler |
| `SOURCE_SCHEDULES` | — | JSON-Map pro Quelle, z. B. `{"noaa":10,"usgs":5}` |
| `*_INTERVAL_MINUTES` | — | Pro-Quelle-Override (`NOAA_INTERVAL_MINUTES`, `USGS_INTERVAL_MINUTES`, …) |
| `SCHEDULER_GENERATE_BRIEFING` | `true` | Briefing auf separatem `INGEST_INTERVAL_MINUTES`-Loop |
| `SCHEDULER_STARTUP_DELAY_SECONDS` | `30` | Wartezeit bis erster Scheduler-Ingest (nach Startup-Pipeline) |
| `OBSERVED_EVENTS_RETENTION_DAYS` | `90` | Inaktive Observed Events löschen nach N Tagen |
| `ALERTS_RETENTION_DAYS` | `30` | Inaktive Alerts löschen nach N Tagen |
| `RETENTION_CLEANUP_ENABLED` | `true` | Retention beim Start + täglich |
| `CORRELATION_AUTO_RUN` | `true` | Korrelation nach Ingest (Startup + Scheduler) |
| `EXPOSURE_AUTO_IMPORT` | `true` | Exposure-Fixtures importieren wenn `assets` leer |
| `EXPOSURE_AUTO_RUN` | `false` | Exposure-Berechnung nach Korrelation |
| `IMPLICATIONS_AUTO_RUN` | `false` | Implications nach Exposure-Berechnung |
| `SHOWCASE_MODE` | `false` | Kuratierte Demo-Szenarien statt Live-Ingest |
| `LOG_LEVEL` | `INFO` | Log-Level |
| `LOG_FORMAT` | `json` | `json` (structured) oder `text` (lesbar) |

Vollständige Liste: [.env.example](.env.example)

## Automatischer Daten-Refresh

**Standard in Docker Compose:** Beim Container-Start läuft die **Startup-Pipeline** sofort; danach pollt der **Per-Source-Scheduler** jede Quelle in `SOURCES_LIVE` auf eigenem Intervall; Briefing läuft separat alle `INGEST_INTERVAL_MINUTES`. **n8n ist nicht erforderlich** — siehe [docs/n8n-integration.md](docs/n8n-integration.md).

### Startup-Pipeline (einmalig beim Start)

| Schritt | Bedingung | Aktion |
|---------|-----------|--------|
| Migrationen | immer | `alembic upgrade head` (Entrypoint) |
| Alert-Cleanup | `STARTUP_PIPELINE_ENABLED=true` | Abgelaufene + Fixture-Alerts deaktivieren |
| Exposure-Import | `assets` leer **oder** `EXPOSURE_AUTO_IMPORT=true` | `fixtures/exposure/` laden |
| Showcase-Ingest | `SHOWCASE_MODE=true` | Kuratierte Szenarien + Korrelation + Exposure + Implications + Briefing |
| Live-Ingest | `DEMO_MODE=false` und nicht Showcase | Alle `SOURCES_LIVE`-Quellen |
| Korrelation | `CORRELATION_AUTO_RUN=true` | Nach erfolgreichem Ingest |
| Exposure | `EXPOSURE_AUTO_RUN=true` | Nach Korrelation |
| Implications | `IMPLICATIONS_AUTO_RUN=true` | Nach Exposure |
| Briefing | `AUTO_GENERATE_BRIEFING=true` | Nach Ingest |

`DEMO_MODE=true`: Startup-Pipeline deaktiviert nur Alerts; Ingest manuell per CLI.

```env
STARTUP_PIPELINE_ENABLED=true
SCHEDULER_ENABLED=true
AUTO_GENERATE_BRIEFING=true
CORRELATION_AUTO_RUN=true
EXPOSURE_AUTO_IMPORT=true
```

### Periodischer Scheduler (per-source)

| Methode | Wann nutzen |
|---------|-------------|
| **Backend-Scheduler** (`SCHEDULER_ENABLED=true`) | **MVP-Standard** — Container-Deployment ohne externe Tools |
| **cron / systemd timer** | Host mit Docker Compose, Scheduler deaktiviert |
| **n8n** (optional) | Externe Orchestrierung, Benachrichtigungen, Custom-Workflows |

```env
SCHEDULER_ENABLED=true
INGEST_INTERVAL_MINUTES=15
SCHEDULER_GENERATE_BRIEFING=true
SCHEDULER_STARTUP_DELAY_SECONDS=30
SOURCE_SCHEDULES={"noaa":10,"usgs":5,"gdacs":10,"nina":15}
# oder: USGS_INTERVAL_MINUTES=5
```

Jede Quelle in `SOURCES_LIVE` läuft in einem eigenen asyncio-Loop mit konfigurierbarem Intervall (`SOURCE_SCHEDULES` JSON oder `*_INTERVAL_MINUTES`). Briefing-Generierung nutzt `INGEST_INTERVAL_MINUTES` als separates Intervall. Empfohlene Intervalle: [docs/data-sources.md](docs/data-sources.md).

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
| 0 | Repository Assessment & Showcase-Erweiterung | ✅ |
| 1 | Planung & Dokumentation | ✅ |
| 2 | Backend, PostgreSQL/PostGIS, Fixtures, Basis-API | ✅ |
| 3 | Live NOAA source, bounding_box filter | ✅ |
| 4 | Dashboard (MapLibre GL JS) | ✅ |
| 5 | Regelbasierte Analyse & Fallback-Briefing | ✅ |
| 6 | LLM Cross-Alert-Integration | ✅ |
| 7 | Live NINA & GDACS, LLM Evidence Package | ✅ |
| 8 | SHOWCASE_MODE, Multi-Layer Dashboard, Event Detail | ✅ |
| 9 | Per-source Scheduler, Retention, Security, CI | ✅ |

## Bekannte Limitierungen

| Limitierung | Hinweis |
|-------------|---------|
| Static Admin Token | Kein OAuth/Rotation — starkes Token setzen (`ADMIN_TOKEN` ≥ 32 Zeichen) |
| Kein WAF / Rate Limiting | Öffentliche API ungeschützt — Reverse-Proxy empfohlen |
| LLM optional | Standard regelbasiert; LLM-Halluzinationen möglich bei Aktivierung |
| FIRMS live | Erfordert `FIRMS_MAP_KEY`; ohne Key Fixture-Fallback |
| Showcase ≠ Live | `SHOWCASE_MODE=true` lädt kuratierte Demo-Daten, keine amtlichen Warnungen |
| Per-Source-Scheduler | Parallele Ingests pro Quelle — kein globaler Lock (akzeptabel für MVP) |
| Retention | Löscht nur **inaktive** Records — aktive Alerts/Events bleiben unbegrenzt |
| CI ohne Dependabot | `pytest` + `npm run build` only — kein automatisches Dependency-Scanning |

## Lizenz

TBD
