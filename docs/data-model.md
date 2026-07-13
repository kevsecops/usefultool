# Kanonisches Datenmodell

> **Status:** Phase 1 Spezifikation

## Übersicht

Alle Quellen werden in ein einheitliches `Alert`-Modell überführt. Orientierung an [CAP 1.2](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html) für `severity`, `urgency`, `certainty` und `status`.

## Alert (kanonisch)

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `id` | UUID | ja | Interne Primärschlüssel-ID |
| `source` | enum | ja | `nina`, `gdacs`, `noaa` |
| `source_alert_id` | string | ja | ID in der Quell-API |
| `source_url` | string | nein | Link zur Originalmeldung |
| `title` | string | ja | Kurztitel (bevorzugt `de` oder `en`) |
| `description` | text | nein | Volltext (HTML bereinigt) |
| `instruction` | text | nein | Handlungsempfehlungen |
| `country_code` | string(2) | nein | ISO 3166-1 alpha-2 |
| `country_name` | string | nein | Lesbarer Ländername |
| `region` | string | nein | Bundesland, Staat, Provinz |
| `location_name` | string | nein | Betroffenes Gebiet |
| `latitude` | float | nein | Zentroid (WGS84) |
| `longitude` | float | nein | Zentroid (WGS84) |
| `geometry` | GeoJSON | nein | Polygon/MultiPolygon/Point |
| `category` | enum | ja | Siehe Kategorien unten |
| `event_type` | string | nein | Original-Event-Name der Quelle |
| `severity` | enum | ja | `unknown`, `minor`, `moderate`, `severe`, `extreme` |
| `urgency` | enum | nein | CAP-Urgency normalisiert |
| `certainty` | enum | nein | CAP-Certainty normalisiert |
| `status` | enum | ja | `actual`, `exercise`, `test`, `draft`, `unknown` |
| `language` | string | nein | BCP 47, z.B. `de`, `en-US` |
| `issued_at` | datetime (UTC) | ja | Erstausgabe |
| `effective_at` | datetime (UTC) | nein | Wirksam ab |
| `starts_at` | datetime (UTC) | nein | Ereignisbeginn |
| `expires_at` | datetime (UTC) | nein | Ablauf |
| `updated_at_source` | datetime (UTC) | nein | Letzte Änderung in Quelle |
| `ingested_at` | datetime (UTC) | ja | Erst-Ingestion |
| `last_seen_at` | datetime (UTC) | ja | Letzter erfolgreicher Ingest |
| `raw_payload` | JSONB | ja | Unveränderte Quellantwort |
| `fingerprint` | string(64) | ja | SHA-256 Dedup-Key |
| `is_active` | boolean | ja | Aktuell gültig |

### Indizes (geplant)

- `(fingerprint)` UNIQUE
- `(source, source_alert_id)` UNIQUE
- `(is_active, severity, issued_at DESC)`
- `(country_code, category)` WHERE `is_active`
- GIST auf `geometry` (PostGIS) oder Bounding-Box-Spalten (SQLite)

## Enums

### Severity (normalisiert)

| Wert | CAP-Mapping | GDACS-Mapping |
|------|-------------|---------------|
| `unknown` | fehlend / unbekannt | — |
| `minor` | Minor | Green |
| `moderate` | Moderate | Orange (niedrig) |
| `severe` | Severe | Orange (hoch), Red (niedrig) |
| `extreme` | Extreme | Red (hoch) |

### Urgency (CAP 1.2)

| Wert | Bedeutung |
|------|-----------|
| `immediate` | Sofort handeln |
| `expected` | Bald handeln |
| `future` | Zukünftig |
| `past` | Vergangen |
| `unknown` | Nicht angegeben |

### Certainty (CAP 1.2)

| Wert | Bedeutung |
|------|-----------|
| `observed` | Eingetreten / beobachtet |
| `likely` | Wahrscheinlich |
| `possible` | Möglich |
| `unlikely` | Unwahrscheinlich |
| `unknown` | Nicht angegeben |

### Category (normalisiert)

| Wert | Beispiele |
|------|-----------|
| `weather` | Unwetter, Sturm, Hitzewelle |
| `flood` | Hochwasser, Überschwemmung |
| `wildfire` | Waldbrand, Vegetationsbrand |
| `earthquake` | Erdbeben |
| `volcano` | Vulkanausbruch |
| `tsunami` | Tsunami |
| `health` | Trinkwasser, Epidemie |
| `civil` | Bevölkerungsschutz, Evakuierung |
| `infrastructure` | Stromausfall, Verkehr |
| `environmental` | Umweltgefahr |
| `other` | Nicht zuordenbar |

### Status

| Wert | CAP `status` |
|------|--------------|
| `actual` | Actual |
| `exercise` | Exercise |
| `test` | Test |
| `draft` | Draft |
| `unknown` | — |

### Source

| Wert | Beschreibung |
|------|--------------|
| `nina` | Deutschland — NINA/BBK über warnung.bund.de |
| `gdacs` | GDACS international |
| `noaa` | NOAA/NWS USA |

## Fingerprint-Strategie

Ziel: Idempotente Upserts ohne Duplikate bei wiederholten Ingest-Läufen.

```
fingerprint = SHA256(
  source + "|" +
  source_alert_id + "|" +
  normalize(title) + "|" +
  issued_at_iso + "|" +
  severity + "|" +
  category
)
```

**Update-Erkennung:** Wenn `fingerprint` gleich, aber `updated_at_source` oder `version` (NINA) neuer → Update statt Insert.

**Deaktivierung:** Alert nicht mehr in Quell-Liste und `expires_at < now()` → `is_active = false`.

**GDACS-Sonderfall:** `eventid` + `episodeid` als `source_alert_id`; Fingerprint enthält `episodeid`.

**NOAA-Sonderfall:** CAP `id` (URN) als `source_alert_id`; Updates über `messageType=Update` mit gleicher Basis-ID.

## Geometry-Handling

| Quelle | Rohformat | Normalisierung |
|--------|-----------|----------------|
| NINA | GeoJSON Polygon via `/warnings/{id}.geojson` | Direkt übernehmen; bei Fehlen: ARS-Zentroid (optional, Phase 3+) |
| GDACS | Point oder Polygon via API | Point → speichern; für TC/FL zusätzlich `getgeometry` abrufen |
| NOAA | GeoJSON Polygon/MultiPolygon in Feature | Direkt übernehmen; Zentroid via PostGIS `ST_Centroid` |

**Speicherung:**
- PostGIS: `geometry GEOMETRY(Geometry, 4326)`
- SQLite: GeoJSON als TEXT + denormalisierte `bbox_min_lat`, `bbox_max_lat`, `bbox_min_lon`, `bbox_max_lon`

**API-Filter `bounding_box`:** `min_lon,min_lat,max_lon,max_lat` → `ST_Intersects` bzw. BBox-Overlap.

## ObservedEvent (Showcase Phase 1)

Persistierte Beobachtungen aus dedizierten Event-Feeds (z. B. USGS Erdbeben). Separate Pipeline vom Alert-Modell — bestehende `alerts`-API bleibt unverändert.

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `id` | UUID | ja | Primärschlüssel |
| `source` | enum | ja | `usgs` (weitere in späteren Phasen) |
| `source_event_id` | string | ja | ID in der Quell-API |
| `source_url` | string | nein | Link zur Originalmeldung |
| `title` | string | ja | Kurztitel |
| `description` | text | nein | Generierte Beschreibung |
| `event_type` | string | nein | z. B. `earthquake` |
| `category` | enum | ja | Normalisierte Kategorie |
| `severity` | enum | ja | PAGER/significance-basiert (nicht nur Magnitude) |
| `status` | enum | ja | `automatic`, `reviewed`, `deleted`, `unknown` |
| `confidence` | enum | ja | `low`, `medium`, `high` |
| `country_code` | string(2) | nein | ISO 3166-1 alpha-2 |
| `region` | string | nein | Region/Bundesland |
| `location_name` | string | nein | Ortsbeschreibung |
| `latitude` / `longitude` | float | nein | WGS84 Zentroid |
| `geometry` | GeoJSON | nein | Point (PostGIS GIST) |
| `spatial_scope` | enum | ja | Default `local` (für künftige SWPC etc.) |
| `affected_latitude_min/max` | float | nein | Nullable, für globale Events |
| `issued_at` | datetime | ja | Ereigniszeit |
| `starts_at` / `ends_at` | datetime | nein | Gültigkeitsfenster |
| `updated_at_source` | datetime | nein | Letzte Quelländerung |
| `ingested_at` / `last_seen_at` | datetime | ja | Ingest-Metadaten |
| `raw_payload` | JSONB | ja | Unveränderte Quellantwort |
| `source_metadata` | JSONB | nein | magnitude, PAGER, tsunami, etc. |
| `fingerprint` | string(64) | ja | Dedup-Key |
| `is_active` | bool | ja | Noch im aktuellen Feed |

**API:** `GET /api/v1/observed-events`, `GET /api/v1/observed-events/{id}`  
**Mapping:** [usgs-mapping.md](./usgs-mapping.md)

### SourceStatus (persistent)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `source` | string (PK) | z. B. `usgs` |
| `record_type` | string | `alert` oder `observed_event` |
| `is_healthy` | bool | Letzter Health-Check |
| `checked_at` | datetime | |
| `latency_ms` | int | |
| `last_success_at` | datetime | |
| `error_message` | text | |
| `ingest_mode` | string | `live` / `fixture` |
| `records_fetched` | int | Letzter Ingest-Lauf |
| `updated_at` | datetime | |

## Zusätzliche Entitäten (Phase 2+)

### IngestRun

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `id` | UUID | |
| `started_at` | datetime | |
| `finished_at` | datetime | |
| `source` | string | `all` oder einzelne Quelle |
| `alerts_fetched` | int | |
| `alerts_created` | int | |
| `alerts_updated` | int | |
| `alerts_deactivated` | int | |
| `errors` | JSONB | Fehler pro Quelle |
| `status` | enum | `running`, `success`, `partial`, `failed` |

### Briefing

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `id` | UUID | |
| `generated_at` | datetime | |
| `type` | enum | `rule_based`, `llm` |
| `overall_risk_score` | int | 0–100 |
| `overall_confidence` | enum | `low`, `medium`, `high` |
| `content` | JSONB | Strukturiertes Briefing |
| `source_alert_ids` | UUID[] | Referenzen |
| `llm_model` | string | null bei rule_based |

### SourceHealth

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `source` | string | |
| `checked_at` | datetime | |
| `is_healthy` | boolean | |
| `latency_ms` | int | |
| `last_success_at` | datetime | |
| `error_message` | string | |

## Zeitzone-Regel

- **Intern:** UTC in DB und Backend
- **API:** ISO 8601 mit `Z` Suffix
- **Frontend:** Nutzer-lokale Darstellung via `Intl.DateTimeFormat`
