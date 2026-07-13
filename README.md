# Global Risk Intelligence MVP

> **Status: Phase 4 — Next.js Dashboard**  
> PostgreSQL/PostGIS, Live NOAA ingest (`DEMO_MODE=false`), Fixture-Ingest (`DEMO_MODE=true`), Basis-API mit `bounding_box`-Filter, **Next.js Dashboard mit MapLibre GL JS**.

## Produktbeschreibung

**Global Risk Intelligence** aggregiert öffentliche Warnmeldungen aus nationalen und internationalen Systemen, normalisiert sie in ein einheitliches Datenmodell und stellt sie über ein read-only Dashboard dar — inklusive regelbasierter Risikoanalyse und **LLM-gestütztem Global Risk Briefing** mit Cross-Alert-Musteranalyse. Regelbasierte Briefings dienen als Fallback.

**Abgedeckte Gefahren (MVP):** Hochwasser, Unwetter, Waldbrände, Erdbeben, Vulkane, tropische Stürme, Tsunamis, Bevölkerungsschutz, Gesundheitswarnungen.

**Disclaimer:** Das System liefert keine amtlichen Warnungen und keine wissenschaftlich gesicherten Vorhersagen. Es aggregiert und interpretiert transparent öffentlich zugängliche Meldungen.

## Datenquellen (MVP)

| Quelle | Abdeckung | API-Basis |
|--------|-----------|-----------|
| NINA/BBK (MoWaS + DWD) | Deutschland | `https://warnung.bund.de/api31` |
| GDACS | International (Naturgefahren) | `https://www.gdacs.org/gdacsapi` |
| NOAA/NWS (full USA) | USA | `https://api.weather.gov/alerts/active` |

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

# Demo-Daten ingestieren (Fixtures, DEMO_MODE=true in Compose)
docker compose exec backend python -m app.jobs.cli ingest
# oder: make ingest

# Prüfen
curl http://localhost:8000/health
curl http://localhost:3000
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
# Live NOAA ingest (.env: NOAA_USER_AGENT setzen; DEMO_MODE in Compose auf false setzen oder exec überschreiben)
DEMO_MODE=false docker compose exec backend python -m app.jobs.cli ingest --sources noaa

curl http://localhost:8000/api/v1/alerts
curl "http://localhost:8000/api/v1/alerts?bounding_box=-98,32,-96,34&country=US"
```

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

# Live NOAA ingest (requires NOAA_USER_AGENT)
DEMO_MODE=false SOURCES_LIVE=noaa python -m app.jobs.cli ingest --sources noaa
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
| `LLM_ENABLED` | `true` | `false` deaktiviert LLM (Tests/Demo); Architektur: LLM = Kernschicht |
| `LLM_PROVIDER` | `mock` | `mock`, `openai_compat`, `ollama` |
| `LLM_BASE_URL` | — | OpenAI-kompatibler Endpoint |
| `LLM_API_KEY` | — | API-Key (nur Backend) |
| `LLM_MODEL` | `gpt-4o-mini` | Modellname |
| `FRONTEND_URL` | `http://localhost:3000` | CORS-Origin |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend API base URL (browser) |
| `API_URL` | `http://backend:8000` | Server-side API URL (Docker) |
| `NOAA_USER_AGENT` | `GlobalRiskIntelligence/1.0` | Pflicht-Header für NOAA live |
| `NOAA_BASE_URL` | `https://api.weather.gov` | NOAA API base URL |
| `NOAA_FETCH_TIMEOUT_SECONDS` | `30` | HTTP timeout für NOAA |
| `NOAA_USE_FIXTURES` | `false` | NOAA-Fixtures erzwingen |
| `NOAA_FALLBACK_TO_FIXTURES` | `true` | Bei Live-Fehler auf Fixtures zurückfallen |
| `SOURCES_LIVE` | `noaa` | Komma-separierte Live-Quellen |
| `LOG_LEVEL` | `INFO` | Log-Level |

Vollständige Liste: [.env.example](.env.example)

## Demo-Modus

`DEMO_MODE=true` aktiviert Fixture-basierte Daten aus `fixtures/` — funktioniert offline, ohne externe APIs.

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [docs/phase1-plan.md](docs/phase1-plan.md) | Konsolidierter Plan |
| [docs/architecture.md](docs/architecture.md) | Architektur & Module |
| [docs/data-model.md](docs/data-model.md) | Kanonisches Alert-Modell |
| [docs/data-sources.md](docs/data-sources.md) | API-Endpunkte & Mapping |
| [docs/noaa-mapping.md](docs/noaa-mapping.md) | NOAA/NWS → kanonisches Mapping |
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
| 5 | Regelbasierte Analyse & Fallback-Briefing | — |
| 6 | LLM Cross-Alert-Integration | — |
| 7 | Production Hardening, Security Review | — |

## Lizenz

TBD
