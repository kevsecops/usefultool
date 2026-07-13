# Global Risk Intelligence MVP

> **Status: Phase 1 — Planungsdokument**  
> Dieses Repository enthält aktuell **keine lauffähige Anwendung**. Es dokumentiert Architektur, Datenmodell, API-Verträge und Recherche zu realen Warnquellen für den MVP.

## Produktbeschreibung

**Global Risk Intelligence** aggregiert öffentliche Warnmeldungen aus nationalen und internationalen Systemen, normalisiert sie in ein einheitliches Datenmodell und stellt sie über ein read-only Dashboard dar — inklusive regelbasierter Risikoanalyse und optionalem KI-generiertem Global Risk Briefing.

**Abgedeckte Gefahren (MVP):** Hochwasser, Unwetter, Waldbrände, Erdbeben, Vulkane, tropische Stürme, Tsunamis, Bevölkerungsschutz, Gesundheitswarnungen.

**Disclaimer:** Das System liefert keine amtlichen Warnungen und keine wissenschaftlich gesicherten Vorhersagen. Es aggregiert und interpretiert transparent öffentlich zugängliche Meldungen.

## Datenquellen (MVP)

| Quelle | Abdeckung | API-Basis |
|--------|-----------|-----------|
| NINA/BBK | Deutschland | `https://warnung.bund.de/api31` |
| GDACS | International (Naturgefahren) | `https://www.gdacs.org/gdacsapi` |
| NOAA/NWS | USA | `https://api.weather.gov` |

Details: [docs/data-sources.md](docs/data-sources.md)

## Architekturübersicht

```
Externe Warnquellen → Source Adapters → Normalization → Database
    → Rule-based Analysis → [optional LLM] → Read-only API → Dashboard
```

Vollständiges Diagramm: [docs/architecture.md](docs/architecture.md)

## Tech Stack (geplant)

| Komponente | Technologie |
|------------|-------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic |
| Datenbank | PostgreSQL 16 + PostGIS (SQLite für Demo) |
| Frontend | Next.js, TypeScript, Tailwind CSS, MapLibre GL JS |
| LLM | OpenAI-kompatibel, Ollama, Mock-Provider |
| Deployment | Docker Compose (Phase 7) |

## Voraussetzungen (für Phase 2+)

- Python 3.12+
- Node.js 20+ (Frontend, Phase 4)
- Docker & Docker Compose (Phase 7)
- Optional: PostgreSQL 16 mit PostGIS

## Geplanter lokaler Start (Phase 2+)

```bash
# Backend (Phase 2)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
alembic upgrade head
uvicorn app.main:app --reload

# Demo-Modus
DEMO_MODE=true python -m app.jobs.cli ingest

# Frontend (Phase 4)
cd frontend
npm install && npm run dev
```

## Geplanter Docker-Start (Phase 7)

```bash
docker compose up -d
# Dashboard: http://localhost:3000
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Environment-Variablen (Übersicht)

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `DATABASE_URL` | `sqlite:///./data/alerts.db` | DB Connection String |
| `DEMO_MODE` | `false` | Fixtures statt Live-APIs |
| `ADMIN_TOKEN` | — | Token für Admin-Endpunkte |
| `LLM_ENABLED` | `false` | LLM-Briefing aktivieren |
| `LLM_BASE_URL` | — | OpenAI-kompatibler Endpoint |
| `LLM_API_KEY` | — | API-Key (nur Backend) |
| `LLM_MODEL` | `gpt-4o-mini` | Modellname |
| `FRONTEND_URL` | `http://localhost:3000` | CORS-Origin |
| `RISK_SCORE_SCALING` | `50` | Score-Normalisierung |
| `LOG_LEVEL` | `INFO` | Log-Level |

## Demo-Modus

`DEMO_MODE=true` aktiviert Fixture-basierte Daten aus `fixtures/` — funktioniert offline, ohne LLM, mit gefüllter Karte und regelbasiertem Briefing.

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [docs/phase1-plan.md](docs/phase1-plan.md) | Konsolidierter Phase-1-Plan |
| [docs/architecture.md](docs/architecture.md) | Architektur & Module |
| [docs/data-model.md](docs/data-model.md) | Kanonisches Alert-Modell |
| [docs/data-sources.md](docs/data-sources.md) | API-Endpunkte & Mapping |
| [docs/risk-scoring.md](docs/risk-scoring.md) | Risk-Score-Algorithmus |
| [docs/security.md](docs/security.md) | Threat Model & Maßnahmen |

## Bekannte Einschränkungen (MVP)

- Nur 3 Datenquellen (DE, International/Natur, US)
- Kein Echtzeit-Push — Polling-basiert
- LLM-Ausgabe ist interpretativ, nicht amtlich
- NINA-API-Dokumentation ist community-basiert (nicht offiziell von BBK)
- GDACS limitiert auf ~100 Events / 4 Tage im Standard-Endpunkt
- NOAA erfordert User-Agent-Header; Rate-Limits nicht veröffentlicht

## Roadmap

| Phase | Inhalt | Status |
|-------|--------|--------|
| 1 | Planung & Dokumentation | ✅ Aktuell |
| 2 | Backend-Grundlage, Fixtures, Basis-API | Wartet auf Freigabe |
| 3 | Erste Live-Quelle (NOAA) | — |
| 4 | Dashboard (Karte, Liste, Detail) | — |
| 5 | Regelbasierte Analyse & Fallback-Briefing | — |
| 6 | LLM-Integration | — |
| 7 | Weitere Quellen, Docker, Security Review | — |

## Lizenz

TBD
