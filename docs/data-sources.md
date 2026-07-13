# Datenquellen — Recherche & Mapping

> **Status:** Phase 1 — Endpunkte verifiziert am 2026-07-13 via HTTP-Requests  
> **Regel:** Keine erfundenen URLs. Inoffizielle/community-Dokumentation ist gekennzeichnet.

---

## 1. Deutschland — NINA / BBK

### Offiziellkeit

| Aspekt | Bewertung |
|--------|-----------|
| API-Host | **Offiziell** — `warnung.bund.de` (Bundesamt für Bevölkerungsschutz) |
| OpenAPI-Doku | **Community** — [nina.api.bund.dev](https://nina.api.bund.dev/) (bundesAPI, reverse-engineered) |
| CAP-Standard | Warnungsdetails folgen CAP 1.2-ähnlichem JSON-Schema |

### Basis-URL

```
https://warnung.bund.de/api31
```

### Primäre Endpunkte (MVP)

| Endpunkt | Methode | Zweck | Verifiziert |
|----------|---------|-------|-------------|
| `/mowas/mapData.json` | GET | Aktive MoWaS-Bevölkerungsschutz-Warnungen (Kompaktliste) | ✅ 200 |
| `/katwarn/mapData.json` | GET | Katwarn-Meldungen | Dokumentiert |
| `/biwapp/mapData.json` | GET | BIWAPP-Meldungen | Dokumentiert |
| `/dwd/mapData.json` | GET | DWD-Unwetterwarnungen | ✅ (leer zum Testzeitpunkt) |
| `/warnings/{identifier}.json` | GET | Vollständige CAP-Detailwarnung | ✅ 200 |
| `/warnings/{identifier}.geojson` | GET | Geometrie (Polygon) | ✅ 200 |
| `/dashboard/{ARS}.json` | GET | Regionalübersicht nach Amtlichem Regionalschlüssel | ✅ 200 |

**Identifier-Beispiel (live):** `mow.DE-SL-SLS-W038-20260113-000` — echte Trinkwasserwarnung Saarlouis (ID-Datum = Erstmeldung, nicht „stale“)

**Fixture-ID (nur Demo):** `mow.DEMO-SL-FLOOD-20260713-000` — fiktive Hochwasserwarnung, **nicht** auf warnung.bund.de

### Legacy-Endpunkte (nicht primär für MVP)

| Endpunkt | Hinweis |
|----------|---------|
| `https://warnung.bund.de/bbk.mowas/{id}.json` | Ältere API-Struktur; ETag-Support |
| `https://warnung.bund.de/bbk.config/config_rel.json` | Konfiguration |
| `https://warnung.bund.de/bbk.status/status_{ARS}.json` | Status pro Region |

> Empfehlung: **api31** verwenden; Legacy nur als Fallback dokumentieren.

### Response-Formate

**mapData.json** (Kompaktliste):
```json
[{
  "id": "mow.DE-SL-SLS-W038-20260113-000",
  "version": 11,
  "startDate": "2026-01-13T12:09:37+01:00",
  "severity": "Minor",
  "urgency": "Immediate",
  "type": "Update",
  "i18nTitle": { "de": "...", "en": "..." },
  "transKeys": { "event": "BBK-EVC-069" }
}]
```

**warnings/{id}.json** (CAP-Detail):
- Felder: `identifier`, `sender`, `sent`, `status`, `msgType`, `info[]` mit `severity`, `urgency`, `certainty`, `category`, `event`, `headline`, `description`, `area[]`
- HTML in `description` (`<br/>` Tags)

**warnings/{id}.geojson**:
- `FeatureCollection` mit `Polygon` und `properties.warnId`

### Auth, Rate Limits, Caching

| Aspekt | Wert |
|--------|------|
| Authentifizierung | Keine |
| Rate Limits | Nicht dokumentiert; konservativ: max. 1 Request/10s pro Endpunkt |
| Caching | `ETag` + `Cache-Control: max-age=10` — Conditional GET empfohlen |
| User-Agent | Nicht explizit gefordert, aber sinnvoll setzen |

### Adapter-Strategie

1. `fetch_alerts()`: `GET /mowas/mapData.json` + optional `/dwd/mapData.json`
2. Für jeden Eintrag: `GET /warnings/{id}.json` + `/warnings/{id}.geojson`
3. `parse_alert()`: CAP-JSON → ParsedAlert
4. `normalize_alert()`: Severity direkt aus CAP; Category aus `BBK-EVC-*` Event-Codes oder `category[]`
5. `health_check()`: `GET /mowas/mapData.json` mit Timeout 10s

### Mapping-Notizen

| Quellfeld | Kanonisch |
|-----------|-----------|
| `id` | `source_alert_id` |
| `i18nTitle.de` / `.en` | `title` |
| `info[0].description` | `description` (HTML sanitizen) |
| `info[0].severity` | `severity` (CAP → lowercase) |
| `info[0].urgency` | `urgency` |
| `info[0].certainty` | `certainty` |
| `sent` | `issued_at` |
| `version` | Update-Erkennung |
| GeoJSON | `geometry`, Zentroid berechnen |
| — | `country_code` = `DE` |

### Bekannte Limitierungen

- Keine offizielle OpenAPI von BBK; Community-Doku kann hinterherhinken
- `dashboard/{ARS}` liefert leer für Berlin (110000000000) — regionale Abdeckung variiert
- DWD-Warnungen zeitweise leer (saisonal)
- Mehrere parallele Feeds (mowas, katwarn, biwapp) können Überlappungen erzeugen → Dedup wichtig

### Fixture-Strategie

`fixtures/nina/`:
- `mapdata_mowas.json` — 3–5 Demo-Einträge (Hochwasser, Waldbrand, Trinkwasser)
- `warning_detail_{id}.json` — CAP-Detail pro Fixture
- `warning_geo_{id}.geojson` — Polygon um deutsche Region

**Wichtig:** Demo-Fixtures verwenden `mow.DEMO-*`-IDs, **keine echten NINA-IDs**. Echte IDs (z. B. `mow.DE-SL-SLS-W038-20260113-000`) können monatelang in `mapData.json` bleiben — das Datumssegment ist die Erstmeldung, nicht das Ablaufdatum.

### Live vs. Fixture (Konfiguration)

| Modus | Bedingung | NINA-Verhalten |
|-------|-----------|----------------|
| **Demo** | `DEMO_MODE=true` (docker-compose Default) | Nur `fixtures/nina/`, `ingest_mode=fixture`, kein `source_url` |
| **Live** | `DEMO_MODE=false` + `nina` in `SOURCES_LIVE` | Nur warnung.bund.de API, `ingest_mode=live` |
| **Fallback** | `NINA_FALLBACK_TO_FIXTURES=true` (Default: **false**) | Fixtures **nur** bei komplettem Live-Fetch-Fehler oder leerer Antwort — **kein Merge** mit Live-Daten |

Bei Live-Ingest werden alle aktiven NINA-Alerts deaktiviert, deren `source_alert_id` nicht in der aktuellen Fetch-Menge ist. Nach Wechsel von Demo → Live verschwinden daher Demo-Fixture-Warnungen beim nächsten Ingest.

`GET /api/v1/sources` liefert pro Quelle `ingest_mode` (`fixture` / `live`) und `alerts_fetched`.

---

## 2. International — GDACS

### Offiziellkeit

| Aspekt | Bewertung |
|--------|-----------|
| API | **Offiziell** — [Swagger UI](https://www.gdacs.org/gdacsapi/swagger/index.html) |
| Dokumentation | [GDACS API Quickstart v2 (PDF)](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v2.pdf) |
| RSS | **Offiziell** — `https://www.gdacs.org/xml/rss.xml` |

### Primäre Endpunkte (MVP)

| Endpunkt | Methode | Zweck | Verifiziert |
|----------|---------|-------|-------------|
| `/gdacsapi/api/events/geteventlist/events4app` | GET | Letzte ~100 Events, letzte 4 Tage | ✅ 200 GeoJSON |
| `/gdacsapi/api/events/geteventlist/SEARCH?{params}` | GET | Gefilterte Suche | ✅ 200 |
| `/gdacsapi/api/events/geteventdata?eventtype={T}&eventid={ID}` | GET | Event-Detail | ✅ 200 |
| `/gdacsapi/api/polygons/getgeometry?eventtype={T}&eventid={ID}&episodeid={E}` | GET | Polygon/Track | Dokumentiert |
| `/xml/rss.xml` | GET | GeoRSS-Feed (Alternative) | ✅ 200 XML |

**Basis:** `https://www.gdacs.org`

**SEARCH-Beispiel:**
```
GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ&limit=10
```

**Event-Typen:** `EQ` (Earthquake), `TC` (Tropical Cyclone), `FL` (Flood), `VO` (Volcano), `WF` (Wildfire), `DR` (Drought)

### Response-Format (events4app)

GeoJSON `FeatureCollection`:
```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": { "type": "Point", "coordinates": [148.52, -3.22] },
    "properties": {
      "eventtype": "EQ",
      "eventid": 1551590,
      "episodeid": 1717883,
      "name": "Earthquake in Papua New Guinea",
      "alertlevel": "Green",
      "alertscore": 1,
      "severitydata": { "severity": 6.4, "severitytext": "Magnitude 6.4M", "severityunit": "M" },
      "country": "Papua New Guinea",
      "iso3": "PNG",
      "fromdate": "2026-07-13T08:53:27",
      "iscurrent": "true",
      "url": { "details": "https://www.gdacs.org/gdacsapi/api/events/geteventdata?..." }
    }
  }]
}
```

### Auth, Rate Limits, Caching

| Aspekt | Wert |
|--------|------|
| Authentifizierung | Keine |
| Rate Limits | Nicht dokumentiert; GDACS empfiehlt Cache-Nutzung und selektive SEARCH-Queries |
| Datenumfang | `events4app`: max. 100 Records / 4 Tage |
| Lizenz | Open data (RSS: "public domain"; API: frei nutzbar laut GDACS-Doku) |

### Adapter-Strategie

1. `fetch_alerts()`: `GET .../events/geteventlist/events4app` (oder SEARCH mit `alertlevel=Orange,Red`)
2. Optional Detail-Fetch für Geometrie bei TC/FL
3. `parse_alert()`: GeoJSON Feature → ParsedAlert
4. `normalize_alert()`:
   - `source_alert_id` = `{eventtype}-{eventid}-{episodeid}`
   - `severity` aus `alertlevel`: Green→minor, Orange→moderate/severe, Red→severe/extreme
   - `category` aus `eventtype`: EQ→earthquake, TC→weather, etc.
   - `country_code` aus `iso3` → ISO2 lookup
5. `health_check()`: `GET events4app` mit Timeout 15s

### Mapping-Notizen

| Quellfeld | Kanonisch |
|-----------|-----------|
| `eventid` + `episodeid` | `source_alert_id` |
| `name` | `title` |
| `description` / `htmldescription` | `description` |
| `alertlevel` | `severity` |
| `eventtype` | `category` + `event_type` |
| `fromdate` | `issued_at` / `starts_at` |
| `datemodified` | `updated_at_source` |
| `geometry` | `geometry` (Point) |
| `url.report` | `source_url` |
| `iscurrent` | `is_active` |

### Bekannte Limitierungen

- Nur Naturkatastrophen (kein Bevölkerungsschutz)
- 100-Event-Limit → für MVP ausreichend; für Vollabdeckung SEARCH mit Pagination
- `iscurrent=false` Events noch in SEARCH sichtbar → filtern
- Alert-Level ist GDACS-eigen, nicht CAP

### Fixture-Strategie

`fixtures/gdacs/`:
- `events4app.json` — EQ (Orange), TC (Red), VO (Green)
- `event_detail_eq.json` — Detail-Response
- `geometry_tc.json` — Cyclone-Track-Polygon

---

## 3. USA — NOAA / National Weather Service

### Offiziellkeit

| Aspekt | Bewertung |
|--------|-----------|
| API | **Offiziell** — [weather.gov API Docs](https://www.weather.gov/documentation/services-web-api) |
| Alerts | [Alerts Web Service](https://www.weather.gov/documentation/services-web-alerts) |
| OpenAPI | `https://api.weather.gov/openapi.json` (zeitweise instabil) |

### Basis-URL

```
https://api.weather.gov
```

### Primäre Endpunkte (MVP)

| Endpunkt | Methode | Zweck | Verifiziert |
|----------|---------|-------|-------------|
| `/alerts/active` | GET | Alle aktiven Warnungen (USA) | ✅ 200 |
| `/alerts/active?area={STATE}` | GET | Aktive Warnungen pro US-Bundesstaat | ✅ 200 (TX: 5 Alerts) |
| `/alerts/active?point={lat},{lon}` | GET | Alerts für Koordinate | Dokumentiert |
| `/alerts/active?zone={UGC}` | GET | Alerts für Zone/County | Dokumentiert |
| `/alerts` | GET | Historie (7 Tage) | Dokumentiert |
| `/alerts/{id}` | GET | Einzelwarnung | Dokumentiert |

**Hinweis:** `/alerts/active` redirectet intern zu `/alerts?active=true`.

**CAP XML Alternative:** `Accept: application/cap+xml` oder `application/atom+xml`

### Response-Format

GeoJSON `FeatureCollection` (JSON-LD):
```json
{
  "type": "FeatureCollection",
  "features": [{
    "id": "https://api.weather.gov/alerts/urn:oid:...",
    "geometry": { "type": "Polygon", "coordinates": [[...]] },
    "properties": {
      "id": "urn:oid:...",
      "event": "Flood Advisory",
      "severity": "Minor",
      "urgency": "Expected",
      "certainty": "Likely",
      "headline": "Flood Advisory issued...",
      "description": "* WHAT...",
      "instruction": "Turn around, don't drown...",
      "areaDesc": "Tarrant, TX",
      "sent": "2026-07-13T03:33:00-05:00",
      "effective": "...",
      "expires": "...",
      "status": "Actual",
      "messageType": "Alert",
      "category": "Met"
    }
  }]
}
```

### Auth, Rate Limits, Caching

| Aspekt | Wert |
|--------|------|
| Authentifizierung | Keine (API-Key geplant für Zukunft) |
| **User-Agent** | **Pflicht** — ohne UA → HTTP 403 |
| Rate Limits | Nicht veröffentlicht; Empfehlung: max. 1 Request/30s |
| Rate-Limit-Fehler | HTTP 403 mit Reference ID (nicht 429) |
| Caching | `Cache-Control: max-age=5` für `/alerts/active` |
| Kontakt bei Sperre | sdb.support@noaa.gov |

**Empfohlener User-Agent:**
```
GlobalRiskIntelligence/1.0 (contact@example.com)
```

### Adapter-Strategie

1. `fetch_alerts()`: `GET /alerts/active` (paginated via `pagination.next` / `Link` header)
2. `parse_alert()`: GeoJSON Feature → ParsedAlert
3. `normalize_alert()`:
   - CAP `severity`, `urgency`, `certainty` direkt mappen
   - `event` → `event_type`; Category aus Event-Name (Flood→flood, Tornado→weather, etc.)
   - `areaDesc` → `location_name`, `region`
   - `country_code` = `US`
4. `health_check()`: `GET /alerts/active?area=DC` mit UA-Header

Vollständige Mapping-Tabelle: [docs/noaa-mapping.md](noaa-mapping.md)

### Live-Integration (Phase 7)

| Quelle | Adapter | Status |
|--------|---------|--------|
| NOAA | `backend/app/sources/noaa.py` | ✅ Live + Fixtures |
| NINA | `backend/app/sources/nina.py` | ✅ Live + Fixtures |
| GDACS | `backend/app/sources/gdacs.py` | ✅ Live + Fixtures |

Mapping-Dokumentation:
- [docs/noaa-mapping.md](noaa-mapping.md)
- [docs/nina-mapping.md](nina-mapping.md)
- [docs/gdacs-mapping.md](gdacs-mapping.md)

Deployment und Scheduling: [docs/deployment.md](deployment.md), [docs/n8n-integration.md](n8n-integration.md)

### Mapping-Notizen

| Quellfeld | Kanonisch | Implementierung |
|-----------|-----------|-----------------|
| `properties.id` | `source_alert_id` | `noaa.py:parse_alert()` |
| `properties.event` | `event_type` | direkt |
| `properties.event` | `category` | `normalize_event_name()` |
| `properties.headline` | `title` | mit Fallback |
| `properties.description` | `description` | `sanitize_html()` |
| `properties.instruction` | `instruction` | `sanitize_html()` |
| `properties.severity` | `severity` | `normalize_cap_severity()` |
| `properties.urgency` | `urgency` | Enum-Map |
| `properties.certainty` | `certainty` | Enum-Map |
| `properties.sent` | `issued_at` | `parse_datetime()` |
| `properties.effective` | `effective_at` | `parse_datetime()` |
| `properties.expires` | `expires_at` | `parse_datetime()` |
| `geometry` | `geometry` | GeoJSON direkt |
| `geometry` | `latitude`, `longitude` | `compute_centroid()` |
| `properties.areaDesc` | `location_name` | direkt |
| Feature `id` / `@id` | `source_url` | `resolve_source_url()` |
| — | `country_code` | `US` |

### Bekannte Limitierungen

- Nur USA (+ Territorien)
- Zone-Query liefert keine County-basierten Polygon-Warnungen → Point-Query bevorzugen für Vollständigkeit
- Keine Tornado-Watch SEL-Sprache in `/alerts/active`
- Alaska Marine Alerts fehlen in CAP 1.2
- Sehr hohes Volumen bei `/alerts/active` (alle USA) → State-weise oder mit Filtern

### Fixture-Strategie

`fixtures/noaa/`:
- `alerts_active_tx.json` — Flood Advisory, Severe Thunderstorm Warning
- `alerts_active_ca.json` — Wildfire Warning
- `alert_detail.json` — Einzelnes Feature

---

## 4. NASA EONET — Natural Events (Showcase Phase 2)

### Offiziellkeit

| Aspekt | Bewertung |
|--------|-----------|
| API | **Offiziell** — [NASA EONET API v3](https://eonet.gsfc.nasa.gov/docs/v3) |
| Host | `eonet.gsfc.nasa.gov` |

### Primäre Endpunkte

| Endpunkt | Methode | Zweck | Verifiziert |
|----------|---------|-------|-------------|
| `/api/v3/events?status=open` | GET | Aktive Naturereignisse | ✅ 200 |
| `/api/v3/events/{id}` | GET | Event-Detail inkl. Geometrie-Historie | ✅ 200 |
| `/api/v3/categories` | GET | Kategorie-Taxonomie | ✅ 200 |

**Basis:** `https://eonet.gsfc.nasa.gov/api/v3`

Mapping: [docs/eonet-mapping.md](eonet-mapping.md)  
Fixtures: `fixtures/eonet/events_open.json`

---

## 5. NOAA SWPC — Space Weather (Showcase Phase 2)

### Offiziellkeit

| Aspekt | Bewertung |
|--------|-----------|
| API | **Offiziell** — [NOAA SWPC](https://www.swpc.noaa.gov/) |
| Host | `services.swpc.noaa.gov` |

**Hinweis:** Separater Adapter `noaa_swpc` — nicht zu verwechseln mit `noaa` (NWS).

### Primäre Endpunkte

| Endpunkt | Methode | Zweck | Verifiziert |
|----------|---------|-------|-------------|
| `/products/noaa-scales.json` | GET | G/S/R-Skalen (aktuell + Prognose) | ✅ 200 |
| `/products/alerts.json` | GET | Aktive SWPC Alerts/Warnings | ✅ 200 |

**Basis:** `https://services.swpc.noaa.gov/products`

Dokumentation: [docs/space-weather.md](space-weather.md), [docs/noaa-swpc-mapping.md](noaa-swpc-mapping.md)  
Fixtures: `fixtures/noaa_swpc/conditions.json`

---

## 6. NASA FIRMS — Active Fire Clusters (Showcase Phase 3)

### Offiziellkeit

| Aspekt | Bewertung |
|--------|-----------|
| API | **Offiziell** — [NASA FIRMS / LANCE](https://firms.modaps.eosdis.nasa.gov/) |
| Host | `firms.modaps.eosdis.nasa.gov` |
| Auth | Free `MAP_KEY` (email registration) |

**Kritisch:** FIRMS liefert viele Punkt-Detektionen. Der Adapter clustert **während Ingest** und speichert nur Aggregate als `observed_events` (`event_type=active_fire_cluster`).

### Primärer Endpunkt

| Endpunkt | Methode | Zweck | Verifiziert |
|----------|---------|-------|-------------|
| `/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}` | GET | Thermal anomalies (CSV) | ✅ (mit MAP_KEY) |
| `/api/map_key/{MAP_KEY}` | GET | Key status / rate-limit | ✅ |

**Basis:** `https://firms.modaps.eosdis.nasa.gov`

**Default:** `VIIRS_SNPP_NRT`, Area `0,36,20,46` (Südeuropa/Mittelmeer), `DAY_RANGE=1`

Dokumentation: [docs/firms-mapping.md](firms-mapping.md), [docs/fire-clustering.md](fire-clustering.md)  
Fixtures: `fixtures/firms/mediterranean_points.json`

---

## Quellenvergleich

| Kriterium | NINA | GDACS | NOAA | USGS | EONET | NOAA SWPC | FIRMS |
|-----------|------|-------|------|------|-------|-----------|-------|
| Offiziell | Host ja | Ja | Ja | Ja | Ja | Ja | Ja |
| Record type | alert | alert | alert | observed_event | observed_event | observed_event | observed_event |
| Format | JSON (CAP-like) | GeoJSON | GeoJSON | GeoJSON | JSON | JSON | CSV → cluster |
| Geo-Detail | Polygon | Point/Polygon | Polygon | Point | Point/Line/Polygon | Global/zonal | Cluster polygon |
| Abdeckung | DE | Global (Natur) | US | Global (EQ) | Global (Natur) | Global (Raumwetter) | Konfigurierbare Area |
| DEMO_MODE | Fixtures | Fixtures | Fixtures | Fixtures | Fixtures | Fixtures | Fixtures |

## Ingest-Polling-Empfehlung (Phase 7 + Showcase)

| Quelle | Mindestintervall | Begründung |
|--------|------------------|------------|
| NOAA NWS | 30–60s | Cache max-age=5, Rate-Limit-Vorsicht |
| NOAA SWPC | 5–15 min | Alerts ändern sich schneller als Skalen |
| NINA | 60–120s | Cache max-age=10, Detail-Fetches |
| GDACS | 300s | Langsamere Event-Entwicklung |
| USGS | 60–300s | Feed aktualisiert häufig |
| EONET | 300–900s | Open-Feed ausreichend |
| FIRMS | 300–900s | Area-CSV; cluster during ingest; MAP_KEY rate limits |

**Gesamt-Ingest (alle Quellen):** Mindestens **15 Minuten** empfohlen (`INGEST_INTERVAL_MINUTES=15`). Schnellere Intervalle nur mit quellenspezifischem Scheduling (z. B. n8n) und unter Beachtung der Limits oben.

Automatisierung:
- **Eingebaut:** `SCHEDULER_ENABLED=true` im Backend-Container ([docs/deployment.md](deployment.md))
- **Extern:** cron, systemd, n8n ([docs/n8n-integration.md](n8n-integration.md))
