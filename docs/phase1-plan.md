# Phase 1 Plan — Global Risk Intelligence MVP

> **Datum:** 2026-07-13  
> **Status:** Phase 2 freigegeben — Entscheidungen unten eingearbeitet

---

## 1. Repository-Struktur (vollständig)

```
usefultool/
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml              # Phase 2: postgres + backend
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── data-sources.md
│   ├── risk-scoring.md
│   ├── security.md
│   ├── phase1-plan.md              # dieses Dokument
│   ├── llm-analysis.md             # LLM Kern-Analyseschicht
│   ├── deployment.md               # Phase 7
│   └── n8n-integration.md          # Phase 7
├── backend/
│   ├── Dockerfile                  # Phase 7
│   ├── pyproject.toml              # Phase 2
│   ├── alembic.ini                 # Phase 2
│   └── app/
│       ├── __init__.py
│       ├── main.py                 # FastAPI entry
│       ├── api/
│       │   ├── __init__.py
│       │   ├── deps.py
│       │   ├── v1/
│       │   │   ├── alerts.py
│       │   │   ├── briefings.py
│       │   │   ├── stats.py
│       │   │   ├── sources.py
│       │   │   └── admin.py
│       │   └── health.py
│       ├── core/
│       │   ├── config.py
│       │   ├── logging.py
│       │   └── security.py
│       ├── db/
│       │   ├── session.py
│       │   └── base.py
│       ├── models/
│       │   ├── alert.py
│       │   ├── briefing.py
│       │   └── ingest_run.py
│       ├── schemas/
│       │   ├── alert.py
│       │   ├── briefing.py
│       │   ├── stats.py
│       │   └── common.py
│       ├── services/
│       │   ├── alert_service.py
│       │   ├── ingest_service.py
│       │   ├── briefing_service.py
│       │   └── stats_service.py
│       ├── sources/
│       │   ├── base.py
│       │   ├── nina.py
│       │   ├── gdacs.py
│       │   ├── noaa.py
│       │   └── fixture_loader.py
│       ├── normalization/
│       │   ├── severity.py
│       │   ├── category.py
│       │   ├── geometry.py
│       │   └── html_sanitizer.py
│       ├── analysis/
│       │   ├── risk_score.py
│       │   ├── clustering.py
│       │   ├── trends.py
│       │   └── rule_briefing.py
│       ├── llm/
│       │   ├── provider.py
│       │   ├── openai_compat.py
│       │   ├── ollama.py
│       │   ├── mock.py
│       │   └── prompts.py
│       ├── jobs/
│       │   ├── cli.py
│       │   └── scheduler.py
│       └── tests/
│           ├── conftest.py
│           ├── test_sources/
│           ├── test_normalization/
│           ├── test_analysis/
│           ├── test_api/
│           └── test_llm/
├── frontend/
│   ├── Dockerfile                  # Phase 7
│   ├── package.json                # Phase 4
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                # Dashboard
│   │   ├── map/page.tsx
│   │   ├── alerts/page.tsx
│   │   ├── alerts/[id]/page.tsx
│   │   └── briefing/page.tsx
│   ├── components/
│   │   ├── AlertMap.tsx
│   │   ├── AlertList.tsx
│   │   ├── AlertDetail.tsx
│   │   ├── RiskScoreGauge.tsx
│   │   ├── BriefingView.tsx
│   │   └── Filters.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   └── format.ts
│   └── types/
│       ├── alert.ts
│       └── briefing.ts
└── fixtures/
    ├── nina/
    │   ├── mapdata_mowas.json
    │   ├── warning_detail_flood.json
    │   └── warning_geo_flood.geojson
    ├── gdacs/
    │   ├── events4app.json
    │   └── event_detail_eq.json
    └── noaa/
        ├── alerts_active_tx.json
        └── alerts_active_ca.json
```

---

## 2. Architekturübersicht

Monolithisches Backend (FastAPI) + separates Frontend (Next.js) + PostgreSQL/PostGIS.

**Pipeline:** Externe Quellen → Source Adapter → Normalization → DB (Upsert/Dedup) → Analysis → optional LLM → Read-only API → Dashboard.

Siehe [architecture.md](./architecture.md) für Mermaid-Diagramm.

---

## 3. Architekturentscheidungen

| # | Entscheidung | Rationale |
|---|--------------|-----------|
| 1 | **Monolith statt Microservices** | MVP-Komplexität, ein Deployment, einfaches Debugging |
| 2 | **PostgreSQL + PostGIS ab Start** | Geo-Queries nativ; Docker Compose für lokale Entwicklung |
| 3 | **Adapter-Pattern pro Quelle** | Einheitliches Interface, isolierte Quelllogik |
| 4 | **Fingerprint-basierte Dedup** | Idempotente Ingest-Pipeline ohne Duplikate |
| 5 | **LLM als Kern-Analyseschicht** | Cross-Alert-Musteranalyse + Briefing; regelbasierter Fallback bei Ausfall; `LLM_ENABLED=false` für Tests |
| 6 | **DEMO_MODE mit Fixtures** | Offline-Demo, Tests, CI ohne externe Abhängigkeit |
| 7 | **Static Admin Token (MVP)** | Einfach, ausreichend für lokalen Betrieb |
| 8 | **NOAA: Full USA `/alerts/active`** | Ein Endpunkt, keine State-Split-Polling-Strategie für MVP |
| 9 | **NINA: MoWaS + DWD only** | Katwarn/Biwapp aus MVP-Scope |
| 10 | **MapLibre GL JS** | Open Source, keine API-Key-Pflicht (Frontend Phase 4) |
| 11 | **Serverseitiger API-Fetch** | SSRF-Schutz, Rate-Limit-Kontrolle, kein CORS zu Behörden-APIs |

---

## 4. Kanonisches Datenmodell (Kurzfassung)

Einheitliches `Alert`-Objekt mit CAP-orientierten Enums (`severity`, `urgency`, `certainty`), GeoJSON-`geometry`, `fingerprint` für Dedup, `raw_payload` für Forensik.

Vollständige Spezifikation: [data-model.md](./data-model.md)

---

## 5. API-Vertrag

### Öffentlich (Read-Only)

#### `GET /health`
```json
{ "status": "ok", "version": "0.1.0", "db": "connected", "demo_mode": false }
```

#### `GET /api/v1/sources`
```json
{
  "sources": [
    { "id": "nina", "name": "NINA/BBK Germany", "healthy": true, "last_fetch": "..." },
    { "id": "gdacs", "name": "GDACS International", "healthy": true, "last_fetch": "..." },
    { "id": "noaa", "name": "NOAA/NWS USA", "healthy": true, "last_fetch": "..." }
  ]
}
```

#### `GET /api/v1/alerts`

**Query-Parameter:**

| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `source` | string | `nina`, `gdacs`, `noaa` |
| `country` | string | ISO 3166-1 alpha-2 |
| `category` | string | Normalisierte Kategorie |
| `severity` | string | `minor`..`extreme` |
| `active` | bool | Default `true` |
| `issued_after` | datetime | ISO 8601 |
| `issued_before` | datetime | ISO 8601 |
| `bounding_box` | string | `min_lon,min_lat,max_lon,max_lat` |
| `limit` | int | Default 50, max 200 |
| `offset` | int | Pagination |

**Response:**
```json
{
  "items": [ { /* Alert */ } ],
  "total": 142,
  "limit": 50,
  "offset": 0
}
```

#### `GET /api/v1/alerts/{id}`
Einzelne normalisierte Warnung inkl. `raw_payload` (optional via `?include_raw=false`).

#### `GET /api/v1/stats`
```json
{
  "active_count": 42,
  "global_risk_score": 38,
  "score_breakdown": { "base": 30, "cluster_bonus": 5, "trend_mod": 1.1 },
  "by_country": { "US": 18, "DE": 5 },
  "by_category": { "weather": 12, "flood": 8 },
  "by_severity": { "minor": 20, "moderate": 15, "severe": 7 },
  "top_countries": [{"code": "US", "count": 18}],
  "hotspot_regions": [{"region": "Texas, US", "count": 5}],
  "last_ingest": "2026-07-13T09:00:00Z"
}
```

#### `GET /api/v1/briefings/latest`
Aktuellstes Briefing (rule_based oder llm).

#### `GET /api/v1/briefings`
Liste historischer Briefings mit Pagination.

### Admin (Auth: `X-Admin-Token`)

#### `POST /api/v1/admin/ingest`
```json
// Request (optional)
{ "sources": ["noaa"], "force": false }

// Response
{
  "run_id": "uuid",
  "status": "success",
  "alerts_fetched": 45,
  "alerts_created": 3,
  "alerts_updated": 12,
  "alerts_deactivated": 2,
  "errors": []
}
```

#### `POST /api/v1/admin/generate-briefing`
```json
// Request (optional)
{ "type": "auto" }  // "auto" | "rule_based" | "llm"

// Response
{ "briefing_id": "uuid", "type": "rule_based", "generated_at": "..." }
```

---

## 6. Datenfluss (Pipeline-Schritte)

```
1. TRIGGER     Admin-POST / CLI / Cron
2. FETCH       Adapter.fetch_alerts() — HTTP oder Fixture
3. VALIDATE    JSON-Schema / Größenlimit / Status-Code
4. PARSE       Adapter.parse_alert() — Quellformat → ParsedAlert
5. NORMALIZE   Adapter.normalize_alert() — ParsedAlert → CanonicalAlert
6. FINGERPRINT SHA-256 Dedup-Key
7. UPSERT      INSERT new / UPDATE changed / SKIP unchanged
8. DEACTIVATE  Alerts nicht mehr in Quelle + expired → is_active=false
9. ANALYZE     Stats, Risk Score, Cluster, Trends
10. BRIEF      Optional LLM oder rule_based Briefing
11. SERVE      API + Dashboard lesen aus DB
```

**Idempotenz:** Schritt 7 garantiert, dass wiederholte Läufe keine Duplikate erzeugen.

---

## 7. Sicherheitsgrenzen

| Grenze | Regel |
|--------|-------|
| Öffentlich ↔ Backend | Nur GET, CORS auf Frontend |
| Admin ↔ Backend | `X-Admin-Token`, POST only |
| Backend ↔ Externe APIs | Allowlist-Hosts, Timeouts, keine User-URLs |
| Backend ↔ LLM | Normalisierte Daten only, Output-Validierung |
| Backend ↔ DB | Docker-intern, nicht öffentlich |
| Warnungstexte | Untrusted → sanitizen |
| LLM-Output | Untrusted → validieren, kein raw HTML |

Details: [security.md](./security.md)

---

## 8. Offene Fragen / Risiken

| # | Frage / Risiko | Empfehlung | Entscheidung nötig |
|---|----------------|------------|-------------------|
| 1 | NINA: Nur MoWaS oder auch DWD/Katwarn/Biwapp? | MoWaS + DWD für MVP | ✅ **MoWaS + DWD** |
| 2 | NOAA: Alle USA oder State-weise Polling? | `/alerts/active` full USA | ✅ **Full USA** |
| 3 | PostgreSQL ab Start oder SQLite first? | PostgreSQL + PostGIS ab Phase 2 | ✅ **PostgreSQL** |
| 4 | MapLibre vs. Leaflet? | MapLibre (Vektor, Performance) | ✅ **MapLibre** |
| 5 | LLM-Provider Default? | Mock in Demo; OpenAI-kompatibel in Prod | ✅ **Mock / OpenAI-compat** |
| 6 | LLM optional oder Kern? | LLM Kern-Analyseschicht mit Fallback | ✅ **Kern mit Fallback** |
| 6 | NINA Community-Doku vs. fehlende offizielle OpenAPI | Community-Doku nutzen, Endpunkte live verifizieren | Informiert |
| 7 | GDACS 100-Event-Limit ausreichend? | Ja für MVP; SEARCH für Erweiterung | Informiert |
| 8 | Admin-Token-Rotation? | Manuell für MVP; dokumentieren | Später |
| 9 | Geocoding für NINA ohne GeoJSON? | ARS→Koordinaten Lookup-Tabelle (optional) | Phase 3+ |
| 10 | Traefik-Integration Details? | Host-Rules in deployment.md Phase 7 | Später |

---

## 9. Konkrete Phase-2-Schritte

1. **Repo-Setup**
   - `.gitignore`, `.env.example`, `pyproject.toml` (FastAPI, SQLAlchemy, Alembic, HTTPX, Pydantic, pytest)
   - `backend/app/main.py` mit `/health`

2. **Datenbank**
   - SQLAlchemy Models: `Alert`, `IngestRun`, `Briefing`
   - PostGIS `geometry` Spalte via geoalchemy2
   - Alembic initiale Migration
   - `DATABASE_URL=postgresql://...` (Docker Compose Default)

3. **Schemas & Normalization**
   - Pydantic `CanonicalAlert` Schema
   - `severity.py`, `category.py` Mapping-Funktionen
   - `html_sanitizer.py` mit `bleach`

4. **Fixture-Adapter**
   - `fixture_loader.py` liest `fixtures/{source}/`
   - `DEMO_MODE=true` → alle Adapter nutzen Fixtures
   - Realistische Fixtures erstellen (3 Quellen)

5. **Source Interface**
   - `base.py` Protocol
   - Stub-Implementierungen `nina.py`, `gdacs.py`, `noaa.py` (nur Fixture-Pfad)

6. **Ingest Service**
   - `ingest_service.py`: Fetch → Parse → Normalize → Upsert
   - Fingerprint-Logik
   - `IngestRun` Protokollierung

7. **Basis-API**
   - `GET /health`, `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`
   - `GET /api/v1/sources`, `GET /api/v1/stats` (Basis)
   - `POST /api/v1/admin/ingest` mit Token-Auth

8. **Tests**
   - Normalisierung, Fingerprint, Dedup
   - API-Endpunkte mit TestClient
   - Fixture-basierte Source-Tests

9. **CLI**
   - `python -m app.jobs.cli ingest`
   - `python -m app.jobs.cli health`

**Phase-2 Definition of Done:**
- `docker compose up` startet PostgreSQL + Backend
- `pytest` grün
- `DEMO_MODE=true` + `ingest` → Alerts in PostgreSQL
- `GET /api/v1/alerts` liefert normalisierte Fixture-Daten
- Admin-Ingest mit Token funktioniert

---

## API-Recherche — Verifizierte Endpunkte (Zusammenfassung)

| Quelle | URL | Status |
|--------|-----|--------|
| NINA MoWaS | `https://warnung.bund.de/api31/mowas/mapData.json` | ✅ Live |
| NINA DWD | `https://warnung.bund.de/api31/dwd/mapData.json` | ✅ Live |
| NINA Detail | `https://warnung.bund.de/api31/warnings/{id}.json` | ✅ Live |
| NINA Geo | `https://warnung.bund.de/api31/warnings/{id}.geojson` | ✅ Live |
| GDACS Events | `https://www.gdacs.org/gdacsapi/api/events/geteventlist/events4app` | ✅ Live |
| GDACS Search | `https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?...` | ✅ Live |
| GDACS RSS | `https://www.gdacs.org/xml/rss.xml` | ✅ Live |
| NOAA Active | `https://api.weather.gov/alerts/active` | ✅ Live (full USA, UA required) |
