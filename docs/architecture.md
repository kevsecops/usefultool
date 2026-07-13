# Architektur — Global Risk Intelligence MVP

> **Status:** Phase 2 — Backend implementiert (PostgreSQL + PostGIS, Fixture-Ingest, Basis-API)

## Ziel

Das System aggregiert öffentliche Warnmeldungen aus drei Quellen (Deutschland/NINA MoWaS+DWD, GDACS, NOAA/NWS), normalisiert sie in ein kanonisches Modell, speichert sie in PostgreSQL/PostGIS, berechnet regelbasierte Risikometriken und erzeugt ein **LLM-gestütztes Global Risk Briefing** mit Cross-Alert-Musteranalyse. Regelbasierte Briefings dienen als Fallback. Ein read-only Dashboard (Phase 4, MapLibre GL JS) visualisiert Warnungen und Briefings.

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph External["Externe Warnquellen"]
        NINA["NINA/BBK<br/>warnung.bund.de/api31"]
        GDACS["GDACS<br/>gdacs.org/gdacsapi"]
        NOAA["NOAA/NWS<br/>api.weather.gov"]
    end

    subgraph Backend["Backend (FastAPI)"]
        subgraph Sources["Source Adapters"]
            SA_NINA["nina.py"]
            SA_GDACS["gdacs.py"]
            SA_NOAA["noaa.py"]
        end

        subgraph Pipeline["Verarbeitungspipeline"]
            NORM["normalization/"]
            DEDUP["Deduplizierung<br/>(fingerprint)"]
            ANALYSIS["analysis/<br/>Risk Score, Stats"]
            LLM["llm/<br/>Provider-Abstraktion"]
        end

        API["api/<br/>REST v1"]
        JOBS["jobs/<br/>CLI / Scheduler"]
        DB_LAYER["db/ + models/"]
    end

    subgraph Storage["Persistenz"]
        PG[("PostgreSQL 16<br/>+ PostGIS")]
    end

    subgraph Frontend["Frontend (Next.js, Phase 4)"]
        DASH["Dashboard"]
        MAP["Karte<br/>MapLibre GL JS"]
        LIST["Warnungsliste"]
        BRIEF["Briefing-Ansicht"]
    end

    NINA --> SA_NINA
    GDACS --> SA_GDACS
    NOAA --> SA_NOAA

    SA_NINA --> NORM
    SA_GDACS --> NORM
    SA_NOAA --> NORM

    NORM --> DEDUP --> DB_LAYER
    DB_LAYER --> PG
    DB_LAYER --> ANALYSIS
    ANALYSIS --> LLM
    LLM -.->|"Fallback"| ANALYSIS
    ANALYSIS --> API
    LLM --> API
    JOBS --> Sources

    API --> DASH
    API --> MAP
    API --> LIST
    API --> BRIEF

    FIXTURES["fixtures/<br/>DEMO_MODE"] -.-> Sources
```

## Modulgrenzen

| Modul | Verantwortung | Abhängigkeiten |
|-------|---------------|----------------|
| `sources/` | Abruf, Parsing, Quell-spezifisches Mapping | HTTPX, Fixtures |
| `normalization/` | CAP-nahe Normalisierung, Severity/Category-Mapping | `schemas/`, `models/` |
| `db/` | SQLAlchemy Session, Repository-Pattern | PostgreSQL + PostGIS |
| `models/` | ORM-Entitäten (Alert, Briefing, IngestRun) | Alembic |
| `schemas/` | Pydantic Request/Response DTOs | — |
| `analysis/` | Statistiken, Cluster, Risk Score | `models/` |
| `llm/` | **Kern-Analyseschicht** — Cross-Alert-Muster, Briefing; Fallback via `analysis/` | `analysis/` |
| `api/` | HTTP-Endpunkte, Auth-Middleware | alle Services |
| `jobs/` | CLI (`ingest`, `briefing`), Cron-Hooks | `sources/`, `analysis/` |
| `core/` | Config, Logging, Security-Utils | — |

## Tech-Stack-Entscheidungen

| Schicht | Wahl | Begründung |
|---------|------|------------|
| Backend | Python 3.12 + FastAPI | Schnelle API-Entwicklung, Pydantic-Integration, async HTTPX |
| ORM | SQLAlchemy 2.x + Alembic | Bewährt, DB-agnostisch (SQLite ↔ PostgreSQL) |
| DB | PostgreSQL 16 + PostGIS | Geo-Queries (`bounding_box`, `ST_Intersects`); ab Phase 2 |
| Frontend | Next.js 14+ App Router, TypeScript | SSR für SEO/Disclaimer, API-Proxy möglich (Phase 4) |
| Karte | MapLibre GL JS | Open Source, keine Pflicht-API-Keys (Phase 4) |
| HTTP Client | HTTPX | Async, Timeouts, Retry |
| LLM | OpenAI-kompatibel (Prod) + Mock (Demo) | Kernschicht für Cross-Alert-Analyse; `LLM_ENABLED=false` für Tests |
| Deployment | Docker Compose | Postgres + Backend ab Phase 2; Frontend Phase 4 |

## Adapter-Interface

Jede Quelle implementiert `BaseSourceAdapter`:

```python
class BaseSourceAdapter(Protocol):
    source_id: str  # "nina" | "gdacs" | "noaa"

    async def fetch_alerts(self) -> list[RawAlertPayload]: ...
    def parse_alert(self, raw: RawAlertPayload) -> ParsedAlert: ...
    def normalize_alert(self, parsed: ParsedAlert) -> CanonicalAlert: ...
    async def health_check(self) -> SourceHealth: ...
```

`DEMO_MODE=true` ersetzt `fetch_alerts()` durch Fixture-Loader aus `fixtures/{source}/`.

## Datenfluss (Kurz)

1. **Ingest-Trigger** — Cron, CLI oder `POST /admin/ingest`
2. **Fetch** — Adapter holen Rohdaten (oder Fixtures)
3. **Parse** — Quellformat → strukturiertes Zwischenmodell
4. **Normalize** — Zwischenmodell → kanonisches `Alert`
5. **Fingerprint** — Dedup-Key berechnen
6. **Upsert** — Insert oder Update nach `fingerprint`; abgelaufene als `is_active=false`
7. **Analyze** — Stats, Risk Score, Region-Cluster
8. **Briefing** — LLM Cross-Alert-Analyse (primär); regelbasierter Fallback bei Ausfall
9. **Serve** — Read-only API für Dashboard

## API-Schichten

```
┌─────────────────────────────────────┐
│  Öffentlich (read-only)             │
│  GET /health, /api/v1/alerts, ...   │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│  Admin (X-Admin-Token)              │
│  POST /api/v1/admin/ingest          │
│  POST /api/v1/admin/generate-briefing│
└─────────────────────────────────────┘
```

## Nicht-Ziele (MVP)

- Keine Microservices, Kafka, Kubernetes
- Keine Nutzerkonten / OAuth
- Keine Echtzeit-WebSockets
- Keine eigenen ML-Modelle
- Keine garantierte weltweite Abdeckung

## Phasen-Roadmap

| Phase | Inhalt |
|-------|--------|
| 1 | Planung (dieses Dokument) |
| 2 | Backend-Grundlage, PostgreSQL/PostGIS, Fixtures, Basis-API | ✅ |
| 3 | Live-Quellen (NOAA `/alerts/active` full USA, NINA MoWaS+DWD, GDACS) |
| 4 | Dashboard (MapLibre GL JS, Liste, Detail) |
| 5 | Regelbasierte Analyse + Fallback-Briefing |
| 6 | LLM-Integration (Cross-Alert-Musteranalyse) |
| 7 | Weitere Quellen, Security Review, Production Hardening |

## Verwandte Dokumente

- [data-model.md](./data-model.md) — Kanonisches Alert-Modell
- [data-sources.md](./data-sources.md) — API-Endpunkte und Mapping
- [risk-scoring.md](./risk-scoring.md) — Score-Algorithmus
- [security.md](./security.md) — Threat Model
- [phase1-plan.md](./phase1-plan.md) — Konsolidierter Phase-1-Plan
- [llm-analysis.md](./llm-analysis.md) — LLM als Kern-Analyseschicht
