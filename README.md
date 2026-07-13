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

## Schnellstart (Docker)

```bash
# Repository klonen, .env anlegen
cp .env.example .env

# PostgreSQL + Backend + Frontend starten
docker compose up -d

# Migrationen (beim ersten Start automatisch via backend entrypoint)
docker compose exec backend alembic upgrade head

# Demo-Daten ingestieren
docker compose exec backend python -m app.jobs.cli ingest

# Live NOAA ingest (set NOAA_USER_AGENT in .env first)
DEMO_MODE=false docker compose exec backend python -m app.jobs.cli ingest --sources noaa

# API testen
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/alerts
curl "http://localhost:8000/api/v1/alerts?bounding_box=-98,32,-96,34&country=US"
```

- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- **Dashboard: http://localhost:3000**

## Frontend (lokal ohne Docker)

```bash
cd frontend
npm install
cp ../.env.example ../.env   # or set NEXT_PUBLIC_API_URL
npm run dev
```

Dashboard: http://localhost:3000 (Backend muss auf Port 8000 laufen).

```bash
# Production build testen
cd frontend && npm run build && npm start
```

## Lokaler Start (ohne Docker)

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
# Mit laufender PostgreSQL-Instanz
cd backend && pytest -v

# Oder im Container
docker compose exec backend pytest -v
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
