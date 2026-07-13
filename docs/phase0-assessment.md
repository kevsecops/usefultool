# Phase 0 — Repository Assessment (Showcase-Erweiterung)

> **Datum:** 2026-07-13  
> **Scope:** Erweiterung des abgeschlossenen MVP (Phase 7) um Event-Schicht, Exposure-Daten und **SHOWCASE_MODE** für Demo-/Präsentationsbetrieb  
> **Status:** Nur Assessment — **keine Anwendungscode-Änderungen** in Phase 0

---

## Ausgangslage

| Merkmal | Ist-Zustand im Repo |
|---------|---------------------|
| MVP-Phasen 1–7 | ✅ abgeschlossen (Live NINA, GDACS, NOAA; Docker; Scheduler) |
| Kern-Entität | Einzelne **`alerts`**-Zeilen (`models/alert.py`), kein Event-Layer |
| Ingest | `ingest_service.py` — Fetch → Parse → Normalize → Upsert/Dedup per Fingerprint |
| Scheduler | Global alle **15 Minuten** (`INGEST_INTERVAL_MINUTES=15`, `SCHEDULER_ENABLED=true` in Compose) |
| Frontend-Routen | `/`, `/map`, `/alerts`, `/alerts/[id]`, `/briefing` |
| LLM | Implementiert (`llm/`), **`LLM_ENABLED=false`** by default |
| **SHOWCASE_MODE** | **Nicht vorhanden** (weder Config noch UI) |
| **observed_events / canonical_events / exposure** | **Keine Tabellen, keine Services** |

Dieses Dokument bewertet die Erweiterung auf Basis des **tatsächlichen Codestands** und der ursprünglichen User-Spezifikation (Global Risk Intelligence MVP).

---

## 1. Ist-Architektur

### 1.1 Deployment & Laufzeit

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Next.js    │────▶│  FastAPI Backend │────▶│ PostgreSQL 16       │
│  :3000      │ GET │  :8000           │     │ + PostGIS           │
└─────────────┘     └────────┬─────────┘     └─────────────────────┘
                             │
                    asyncio Scheduler (15 min)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
           NINA/BBK       GDACS          NOAA/NWS
         (api31)      (gdacsapi)    (alerts/active)
```

- **Monolithisches Backend** (`backend/app/`), separates **Frontend** (`frontend/`), **Docker Compose** mit Healthchecks.
- **Startup:** `deactivate_expired_alerts()` + `deactivate_fixture_alerts()` wenn `demo_mode=false`.
- **Öffentliche API:** nur `GET`; Admin mit `X-Admin-Token` (`POST /api/v1/admin/ingest`).

### 1.2 Datenpipeline (aktuell)

1. `jobs/scheduler.py` oder CLI/Admin triggert `run_ingest()`.
2. `sources/registry.py` liefert Adapter (`nina`, `gdacs`, `noaa`) — Live oder Fixtures (`DEMO_MODE`, `*_USE_FIXTURES`).
3. Jeder Adapter: `fetch_alerts` → `parse_alert` → `normalize_alert` → `CanonicalAlert` (Pydantic).
4. `ingest_service.py`: Upsert in **`alerts`**, Fingerprint-Dedup, Stale/Expired-Deaktivierung, `IngestRun`-Protokoll.
5. Optional: `generate_briefing()` in derselben Transaktionslogik (`AUTO_GENERATE_BRIEFING` / Scheduler-Flag).
6. Read-Pfad: `alert_service` → REST; `stats_service` / `briefing_service` mit **gleichen Filtern** (aktiv, expired, fixture-Ausschluss in Live-Mode).

### 1.3 Persistenz (aktuell)

| Tabelle / Modell | Zweck |
|------------------|--------|
| `alerts` | Kanonische Warnung pro Quellmeldung (GeoJSON + PostGIS `geometry`) |
| `ingest_runs` | Lauf-Historie, Fehler pro Quelle |
| `briefings` | Snapshots (regelbasiert oder LLM), JSON-Inhalt |

**Nicht vorhanden:** Versionierung von Beobachtungen, quellenübergreifende Events, Exposure-Metriken.

### 1.4 Frontend (aktuell)

- App Router, SSR/Server Components, `lib/api.ts` (Browser: `NEXT_PUBLIC_API_URL`, SSR: `API_URL`).
- **MapLibre GL JS** (`AlertMap.tsx`, `MapPageClient.tsx`).
- Navigation fest in `Header.tsx`: Dashboard, Karte, Warnungen, Briefing.
- Keine Event-, Exposure- oder Showcase-spezifischen Views.

### 1.5 Analyse & Briefing (aktuell)

- `analysis/`: `risk_score.py`, `clustering.py`, `trends.py`, `rule_briefing.py` — arbeiten auf **Alert-Listen**.
- `llm/`: Provider-Abstraktion; bei `llm_enabled=false` ausschließlich regelbasiertes Briefing.
- Konsistenzregeln dokumentiert in `docs/consistency-audit.md` (Fixture/Live-Trennung, effective-active).

---

## 2. Bestehende relevante Komponenten

Diese Bausteine können für die Showcase-Erweiterung **wiederverwendet** werden:

| Bereich | Dateien / Module | Relevanz für Erweiterung |
|---------|------------------|-------------------------|
| Adapter-Pattern | `sources/base.py`, `nina.py`, `gdacs.py`, `noaa.py`, `registry.py` | GDACS liefert bereits `eventid`/`episodeid` in `source_alert_id`; Exposure-Felder liegen teils in `raw_payload`, werden aber nicht modelliert |
| Normalisierung | `normalization/*` (severity, category, geometry, fingerprint, bounding_box) | Basis für `observed_events`-Snapshots und Event-Matching |
| Ingest-Orchestrierung | `services/ingest_service.py`, `models/ingest_run.py` | Hook-Punkt nach Upsert für Observed-Event-Schreibung |
| Geo-Queries | PostGIS in `Alert`, `bounding_box`-Filter in API | Exposure und Event-Geometrie können gleiche Infrastruktur nutzen |
| Clustering | `analysis/clustering.py` | Ausgangspunkt für **canonical_events** (räumlich/zeitlich) |
| Briefing/Stats | `briefing_service.py`, `stats_service.py`, `rule_briefing.py` | Umstellung auf Event-Aggregation in späteren Phasen |
| Scheduler | `jobs/scheduler.py`, `core/config.py` | Erweiterbar um Showcase-Jobs (z. B. kuratierte Seeds) ohne separates n8n |
| Fixture-Infrastruktur | `fixtures/`, `alert_fixture.py`, `fixture_loader.py` | SHOWCASE_MODE kann kuratierte Szenarien ähnlich DEMO_MODE laden |
| Tests | `tests/test_ingest.py`, `test_sources/*`, `test_api/*`, `test_live_mode` | Muster für neue Migration- und API-Tests |
| Dokumentation | `data-model.md`, `architecture.md`, `consistency-audit.md` | Müssen um Event/Exposure-Modell ergänzt werden |

---

## 3. Notwendige Änderungen

### 3.1 Konfiguration

- Neues Flag **`SHOWCASE_MODE`** (und `.env.example` / `docker-compose.yml` Dokumentation).
- Klare Semantik vs. **`DEMO_MODE`**:
  - `DEMO_MODE`: technische Fixture-Quellen für Offline/CI.
  - `SHOWCASE_MODE`: produktionsnahe **kuratierte Demo** (stabile Storyline, optional Overlay auf Live-Daten).
- Optional: `SHOWCASE_SCENARIO_ID`, Pfade zu Showcase-Fixtures.

### 3.2 Datenmodell (neu)

| Entität | Zweck |
|---------|--------|
| **`observed_events`** | Immutable (oder append-only) Snapshot je Ingest-Zyklus pro Alert/Quell-ID — Audit & „was sahen wir wann?“ |
| **`canonical_events`** | Quellenübergreifende bzw. episodenbasierte Gefahren-Events (Titel, Kategorie, Severity, Geometrie, Zeitraum, Status) |
| **`event_alert_links`** (o. ä.) | n:m zwischen `canonical_events` und `alerts` |
| **`exposure_snapshots`** (o. ä.) | Bevölkerung/Exposure-Indizes pro Event (primär GDACS; optional statische Raster später) |

Bestehende **`alerts`**-Tabelle bleibt **API-kompatibel** (kein Breaking Change in Phase 1–3 der Erweiterung).

### 3.3 Services & Pipeline

- **`event_observation_service`**: nach jedem erfolgreichen Alert-Upsert Observed-Event persistieren.
- **`canonicalization_service`**: Regeln + Clustering (GDACS-Event-ID, NOAA-`@id`-Gruppen, NINA-Warnungsketten); Idempotenz.
- **`exposure_service`**: Mapping aus GDACS-Properties / Detail-API in normalisierte Exposure-Felder.
- Erweiterung **`ingest_service`**: nach Alert-Persistenz Event- und Exposure-Schritte (feature-flagged bis stabil).

### 3.4 API (neu, read-only)

- `GET /api/v1/events` — Liste kanonischer Events (Filter: active, category, bbox, showcase-only).
- `GET /api/v1/events/{id}` — Detail inkl. verknüpfte Alerts, Exposure, Observed-Historie (optional paginiert).
- `GET /api/v1/exposure` oder eingebettet in Event-Detail.
- `GET /health` / `admin/status`: Metriken zu Events, Showcase-Modus.

### 3.5 Frontend

- Neue Routen (Zielbild): z. B. `/events`, `/events/[id]`, optional `/showcase` (Story-Ansicht).
- Karte: Layer-Umschaltung **Alerts vs. Events**; Exposure-Badges/Popups.
- Header + Dashboard: Teaser für „Top Events“ und Exposure-Highlights.
- **`NEXT_PUBLIC_SHOWCASE_MODE`** oder API-gesteuerte Anzeige (kein zweites Build nötig, wenn API `showcase` flag liefert).

### 3.6 Briefing & Stats

- Snapshot-Schema erweitern: `canonical_events` + Exposure-Zusammenfassung.
- Regelbasiert zuerst (LLM weiterhin optional); Cross-Event-Narrative ohne LLM möglich.

### 3.7 SHOWCASE_MODE-Verhalten

- Kuratierte Datensätze + definierte „Golden Path“-UI.
- In Live-Umgebung: Filter, der Rauschen reduziert (z. B. nur Events mit Exposure > Schwellwert oder feste Regionen).
- Kein Ersatz für amtliche Warnungen — Disclaimer sichtbar halten.

---

## 4. Risiken (Top 10)

| # | Risiko | Auswirkung | Mitigation |
|---|--------|------------|------------|
| 1 | **Doppelte Wahrheit** (Alerts vs. Events) in UI/API | Inkonsistente Zahlen wie früher bei Fixtures/Live | Einheitliche „effective active“-Regeln; Events als Aggregation, Alerts als Quellwahrheit; Tests analog `consistency-audit.md` |
| 2 | **Fehlmatch** quellenübergreifender Canonicalisierung | Falsche Zusammenführung (z. B. NOAA-Warnungen + GDACS-Episoden) | Konservative Regeln v1: GDACS `eventid` hart; NOAA/NINA nur intra-source; manuelle `split/merge` erst später |
| 3 | **GDACS Exposure** unvollständig oder nur in Detail-API | Leere Exposure in Showcase | Felder aus `events4app` + optional Detail-Fetch; Fallback „unknown“; Dokumentation |
| 4 | **Performance** bei Observed-Event-Append pro Ingest | DB-Wachstum, langsame Queries | Partitionierung/Retention-Policy; Aggregates auf `canonical_events`; Index-Design |
| 5 | **Migration auf produktiver DB** | Downtime / lange Backfill | Additive Tabellen; Backfill asynchron; Feature-Flags |
| 6 | **SHOWCASE vs. DEMO Verwechslung** | Live-Demo zeigt Fixtures | Klare Env-Doku; Health zeigt `showcase_mode` + `demo_mode`; gegenseitige Exklusion oder Prioritätsregeln |
| 7 | **PostGIS amd64-Image** auf ARM-Hosts | Langsame Emulation in Dev | Bereits bekannt (`platform: linux/amd64`); CI auf amd64 |
| 8 | **LLM-Spec vs. Betrieb** (User wollte LLM-Kern, Betrieb ohne LLM) | Showcase-Narrative wirkt „flach“ | Regelbasierte Event-Briefings zuerst; LLM Phase 8+ optional |
| 9 | **Frontend-Komplexität** (Map + zwei Layer) | Map-Resize/Reload-Probleme (historisch) | Stabile `MapPageClient`-Patterns; keine SSR-Geo-Props die ständig invalidieren |
| 10 | **Externe API-Instabilität** (NINA inoffiziell, NOAA Rate Limits) | Leere Showcase | Showcase-Szenario mit Fixtures als Fallback **nur** in SHOWCASE_MODE; Live bleibt unverändert |

---

## 5. Migrationsstrategie

### 5.1 Prinzipien

1. **Additive Evolution** — `alerts` und bestehende Endpunkte unverändert lauffähig halten.
2. **Feature Flags** — Event/Exposure-Pipeline schrittweise aktivieren (`ENABLE_EVENT_LAYER`, später `SHOWCASE_MODE`).
3. **Alembic** — neue Revision(en) für Tabellen + Indizes (GIST auf Event-Geometrie).
4. **Backfill** — optionaler Job: bestehende `alerts` → initiale `canonical_events` (GDACS zuerst, da Event-IDs vorhanden).
5. **Rollback** — Flags aus → System verhält sich wie MVP Phase 7.

### 5.2 Reihenfolge der DB-Migration

```
001_initial (bestehend)
    ↓
002_observed_events
    ↓
003_canonical_events + links
    ↓
004_exposure_snapshots
    ↓
005_indexes + optional materialized views
```

### 5.3 Daten-Retention

- `observed_events`: z. B. 90 Tage rolling (konfigurierbar).
- `canonical_events`: solange `is_active` oder Archiv-Flag.
- Exposure: letzter Stand pro Event + Historie optional.

---

## 6. Betroffene Dateien (neu + geändert)

### 6.1 Neu (Backend)

| Datei | Zweck |
|-------|--------|
| `backend/app/models/observed_event.py` | ORM Observed Event |
| `backend/app/models/canonical_event.py` | ORM Canonical Event |
| `backend/app/models/event_alert_link.py` | Verknüpfung Alert ↔ Event |
| `backend/app/models/exposure_snapshot.py` | Exposure-Daten |
| `backend/app/schemas/event.py` | Pydantic DTOs |
| `backend/app/schemas/exposure.py` | Pydantic DTOs |
| `backend/app/services/event_observation_service.py` | Observed-Event-Schreibung |
| `backend/app/services/canonicalization_service.py` | Event-Bildung/Update |
| `backend/app/services/exposure_service.py` | Exposure-Extraktion |
| `backend/app/services/event_service.py` | Query-Logik für API |
| `backend/app/api/v1/events.py` | REST Events |
| `backend/alembic/versions/002_*.py` … | Migrationen |
| `backend/app/tests/test_events/*.py` | Tests Event-Layer |
| `fixtures/showcase/` | Kuratierte Showcase-Szenarien |

### 6.2 Geändert (Backend)

| Datei | Änderung |
|-------|----------|
| `backend/app/core/config.py` | `showcase_mode`, Feature-Flags |
| `backend/app/services/ingest_service.py` | Hooks nach Upsert |
| `backend/app/sources/gdacs.py` | Exposure-Felder explizit mappen |
| `backend/app/api/v1/__init__.py` | Router registrieren |
| `backend/app/services/briefing_service.py` | Event-basierte Snapshots |
| `backend/app/services/stats_service.py` | Event-Metriken |
| `backend/app/api/health.py` | Modus-Metriken |
| `backend/app/analysis/clustering.py` | Wiederverwendung für Canonicalisierung |
| `.env.example`, `docker-compose.yml` | Neue Env-Vars (Dokumentation) |

### 6.3 Neu (Frontend)

| Datei | Zweck |
|-------|--------|
| `frontend/app/events/page.tsx` | Event-Liste |
| `frontend/app/events/[id]/page.tsx` | Event-Detail |
| `frontend/app/showcase/page.tsx` | Optional: geführte Demo |
| `frontend/components/EventCard.tsx`, `EventMapLayer.tsx`, `ExposurePanel.tsx` | UI-Bausteine |
| `frontend/types/event.ts`, `frontend/types/exposure.ts` | Typen |

### 6.4 Geändert (Frontend)

| Datei | Änderung |
|-------|----------|
| `frontend/components/Header.tsx` | Navigation Events/Showcase |
| `frontend/app/page.tsx` | Event-Teaser |
| `frontend/app/map/page.tsx` / `MapPageClient.tsx` | Event-Layer |
| `frontend/lib/api.ts` | Neue Endpunkte |
| `frontend/types/stats.ts` | Event-Stats |

### 6.5 Dokumentation

| Datei | Änderung |
|-------|----------|
| `docs/data-model.md` | Event/Exposure-Entitäten |
| `docs/architecture.md` | Pipeline-Diagramm erweitern |
| `docs/showcase-mode.md` | **neu** — Betrieb SHOWCASE_MODE |
| `README.md` | Link (bereits ergänzt) |

---

## 7. Komplexitätsschätzung

Schätzung für **ein erfahrenes Full-Stack-Team** (1–2 Personen), inkl. Tests und Doku, **ohne** LLM-Reaktivierung:

| Block | Aufwand (Personentage) | Unsicherheit |
|-------|------------------------|--------------|
| Schema + Migrationen + ORM | 3–5 | niedrig |
| Observed-Event-Pipeline | 2–4 | mittel |
| Canonicalisierung v1 | 5–8 | **hoch** (Domänenlogik) |
| Exposure (GDACS) | 3–5 | mittel |
| REST API + Admin-Metriken | 3–4 | niedrig |
| Frontend Events + Karte | 5–8 | mittel (Map-Stabilität) |
| Briefing/Stats-Integration | 3–5 | mittel |
| SHOWCASE_MODE + Fixtures | 2–4 | niedrig |
| Tests + Konsistenz-Audit Update | 4–6 | mittel |
| **Gesamt** | **30–49 PT** (~6–10 Wochen kalender bei 1 FTE) | |

**Gesamtkomplexität:** **L** (large) relativ zum bestehenden MVP — domänenlogisch anspruchsvoller als Phase 7, weil **neue Aggregationssemantik** über drei heterogene Quellen.

---

## 8. Phasen 1–9 Reihenfolge (Showcase-Erweiterung)

Diese Phasen sind **zusätzlich** zum abgeschlossenen MVP (Roadmap Phase 1–7 in `README.md`). Empfohlene lineare Reihenfolge:

| Erw.-Phase | Inhalt | Abhängigkeiten | DoD-Kriterium |
|------------|--------|----------------|---------------|
| **1** | Assessment (dieses Dokument), Config-Skelett (`SHOWCASE_MODE`, Flags), `.env.example` | — | Doku freigegeben; Flags ohne Verhaltensänderung |
| **2** | DB: `observed_events` + Migration; Schreiben bei Ingest (feature-flag off default) | Phase 1 | Migration läuft; Unit-Tests Upsert-Observation |
| **3** | DB: `canonical_events` + Links; `canonicalization_service` v1 (GDACS-Event-ID, intra-source NOAA/NINA) | Phase 2 | API-intern: Events befüllt nach Ingest |
| **4** | `exposure_snapshots` + GDACS-Mapping; Exposure an Canonical Events | Phase 3 | Exposure sichtbar für GDACS-Events in DB |
| **5** | Öffentliche API `GET /events`, `GET /events/{id}`; Health/Stats erweitert | Phase 3–4 | OpenAPI dokumentiert; pytest grün |
| **6** | Frontend: `/events`, Detail, Karten-Layer; Header-Navigation | Phase 5 | Container-Demo End-to-End |
| **7** | Briefing & Dashboard: Event-basierte Stats, regelbasiertes Briefing v2 | Phase 5 | Konsistenz Events ↔ Briefing ↔ Stats |
| **8** | **SHOWCASE_MODE**: kuratierte Szenarien, gefilterte UI, `/showcase` (optional) | Phase 6–7 | Stabile Demo ohne manuelles CLI |
| **9** | Hardening: Retention, Monitoring, Doku, E2E-Tests, optional LLM auf Events | Phase 8 | `consistency-audit.md` aktualisiert; Showcase produktionsreif |

Parallele Arbeit möglich ab Phase 5 (Frontend-Mock gegen stub API) — empfohlen wird trotzdem **API vor UI**, um Konsistenzfehler zu vermeiden.

---

## 9. Konflikte mit User-Spec und Alternativen

| Thema | User-Spec / Erwartung | Ist / Erweiterungsplan | Alternative |
|-------|----------------------|-------------------------|-------------|
| **Kanonisches Modell** | Ein einheitliches **Alert**-Objekt | Bleibt; Events sind **zusätzliche** Aggregationsebene | Alerts durch Events ersetzen — **abgelehnt** (Breaking API) |
| **LLM als Kern-Analyseschicht** | LLM soll Zusammenhänge analysieren | LLM implementiert, **deaktiviert**; Showcase startet regelbasiert | LLM in Erw.-Phase 9 — **empfohlen** nach stabiler Event-Schicht |
| **Kein manuelles Ingest** | Automatisierung im Container | Scheduler 15 min global ✅ | n8n — **optional**, nicht nötig (User-Feedback) |
| **Traefik in deployment.md** | User deployt Reverse-Proxy selbst | Doku erwähnt Traefik | Traefik-Abschnitt als optional kennzeichnen — **Doku-Anpassung**, kein Code |
| **n8n-Integration** | Verwirrung: redundant zu Scheduler | n8n für externe Orchestrierung dokumentiert | In Doku klar: **Built-in Scheduler ist Default** |
| **SHOWCASE vs. DEMO** | Nicht in Original-MVP-Spec | Zwei Modi nötig für Demo vs. CI | Nur DEMO_MODE — **zu grob** für stabile Präsentation auf Live-Daten |
| **Exposure-Genauigkeit** | Keine „wissenschaftlichen Vorhersagen“ vortäuschen | GDACS-Exposure als **indikativ** labeln | Eigene Bevölkerungsraster — **Out of Scope** v1 |
| **Observed Events Speicher** | Nicht spezifiziert | Append-only, Retention nötig | Nur `raw_payload` in alerts — **unzureichend** für Zeitreihen-Audit |
| **Frontend-Scope** | 8 Dashboard-Elemente (MVP) | MVP erfüllt; Showcase braucht **neue** Views | Alles in `/briefing` packen — **schlechte UX** |
| **PostgreSQL ab Start** | User-Entscheidung Phase 1 | PostgreSQL/PostGIS ✅ | SQLite — **nicht zurück** |

---

## 10. Empfehlung Phase-1-Start (erste Implementierungsphase der Erweiterung)

**Start mit Erweiterungs-Phase 1 + 2 kombiniert (kleines, sicheres Inkrement):**

1. **`SHOWCASE_MODE` und `ENABLE_EVENT_LAYER` in `config.py`** — Default `false`, in `/health` exposen.
2. **Alembic `002_observed_events`** — Schema ohne Aktivierung der Schreiblogik in Produktion.
3. **Hook in `ingest_service`** hinter `ENABLE_EVENT_LAYER=true` — nach jedem Alert-Upsert eine `observed_event`-Zeile.
4. **Tests:** Ingest erzeugt Observed-Events; mit Flag off kein Unterschied zum heutigen Verhalten.
5. **Doku:** `docs/showcase-mode.md` (Stub) + Update `data-model.md` Abschnitt Observed Events.

**Nicht im ersten Sprint:** Canonicalisierung, Frontend-Routen, SHOWCASE-UI — zu viele bewegliche Teile.

**Erfolgskriterium für Go/No-Go Phase 3:** Nach 3–5 Scheduler-Zyklen in Docker sind Observed-Events vollständig, Alerts-Verhalten und öffentliche API identisch zu Phase 7; Speicherwachstum im erwarteten Rahmen.

---

## Anhang A — Verifikation gegen Codestand (2026-07-13)

| Prüfpunkt | Ergebnis |
|-----------|----------|
| Adapter `nina`, `gdacs`, `noaa` | ✅ vorhanden |
| `models/alert.py` + `ingest_service.py` | ✅ |
| Scheduler 15 min | ✅ `ingest_interval_minutes=15` |
| `SHOWCASE_MODE` | ❌ nicht implementiert |
| Tabellen `observed_events`, `canonical_events`, exposure | ❌ |
| Frontend nur `/`, `/map`, `/alerts`, `/briefing` | ✅ |
| `LLM_ENABLED` default false | ✅ `config.py` + Compose |

## Anhang B — Referenzen

- [architecture.md](./architecture.md)
- [data-model.md](./data-model.md)
- [consistency-audit.md](./consistency-audit.md)
- [phase1-plan.md](./phase1-plan.md) (historisch: MVP Phase 1 Planung)
