# Regelbasierte Risiko-Bewertung (Risk Scoring)

> **Status:** Phase 5 implementiert  
> **Disclaimer:** Der Score ist ein heuristischer Aggregationsindikator, keine wissenschaftliche Risikobewertung.

## Ziel

Ein transparenter, nachvollziehbarer **Global Risk Score** (0–100) auf Basis normalisierter Warnungen und berechneter Statistiken. Dient als Dashboard-KPI und als Input für regelbasiertes sowie LLM-Briefing.

**Implementierung:** `backend/app/analysis/risk_score.py`

## Score-Berechnung

### Stufe 1: Alert-Level Score

Jede aktive Warnung erhält einen Basis-Score:

| Severity | Gewicht |
|----------|---------|
| `minor` | 1 |
| `moderate` | 3 |
| `severe` | 6 |
| `extreme` | 10 |
| `unknown` | 1 |

### Stufe 2: Modifikatoren (pro Alert)

| Faktor | Bedingung | Multiplikator |
|--------|-----------|---------------|
| Urgency | `immediate` | ×1.5 |
| Urgency | `expected` | ×1.2 |
| Certainty | `observed` | ×1.3 |
| Certainty | `likely` | ×1.1 |
| Geo-Extent | Polygon > 10.000 km² | ×1.2 |
| Geo-Extent | Polygon > 50.000 km² | ×1.5 |
| Duration | Aktiv > 48h | ×1.1 |
| Duration | Aktiv > 7d | ×1.2 |

```
alert_score = base_weight × urgency_mod × certainty_mod × geo_mod × duration_mod
```

Geo-Fläche wird aus `geometry_json` via Shapely berechnet (equirectangular Näherung am Zentroid).

Dauer basiert auf `effective_at` oder `issued_at` bis `now`.

### Stufe 3: Regionaler Cluster-Bonus

Implementierung: `backend/app/analysis/clustering.py`

Hotspots werden erkannt wenn in einem **100 km Radius** (oder gleichem Land+Region, oder Land+Kategorie) ≥3 aktive Warnungen mit `severity >= moderate` (bzw. severe+ für räumliche/Kategorie-Cluster):

```
cluster_bonus = count(severe_or_extreme) × 2 + count(moderate) × 1
```

### Stufe 4: Trend-Modifikator

Implementierung: `backend/app/analysis/trends.py`

Vergleich aktive Warnungen vs. gleitender 7-Tage-Durchschnitt (basierend auf `ingested_at` im Fenster):

| Verhältnis (aktuell / Ø7d) | Modifikator |
|----------------------------|-------------|
| < 0.8 | ×0.9 (Rückgang) |
| 0.8 – 1.2 | ×1.0 |
| 1.2 – 1.5 | ×1.1 |
| 1.5 – 2.0 | ×1.2 |
| > 2.0 | ×1.3 (ungewöhnliche Häufung) |

Spikes (>150% des Durchschnitts) werden zusätzlich als `trend_anomalies` in Stats/Briefing exponiert.

### Stufe 5: Aggregation → Global Score

```
raw_total = Σ(alert_score) + Σ(cluster_bonus)
normalized = min(100, round(raw_total × trend_mod × 50 / scaling_factor))
```

**`scaling_factor`:** Kalibrierbar via Env `RISK_SCORE_SCALING` (Default: `50`).  
Bei Default und `trend_mod=1` entspricht der Score etwa `raw_total` (bis 100).  
Bei 10 aktiven `severe`-Warnungen ohne Modifikatoren: `10 × 6 = 60` → Score ≈ 60.

### Score-Interpretation (UI)

| Bereich | Label | Farbe |
|---------|-------|-------|
| 0–20 | Low | Grün |
| 21–40 | Moderate | Gelb |
| 41–60 | Elevated | Orange |
| 61–80 | High | Rot |
| 81–100 | Critical | Dunkelrot |

## Statistiken (regelbasierte Analyse)

`GET /api/v1/stats` liefert:

| Metrik | Beschreibung |
|--------|--------------|
| `active_count` | Anzahl `is_active=true` |
| `global_risk_score` | Normalisierter Score 0–100 |
| `score_breakdown` | Vollständige Zusammensetzung inkl. Alert-Details |
| `by_country` | Dict `{country_code: count}` |
| `by_category` | Dict `{category: count}` |
| `by_severity` | Dict `{severity: count}` |
| `top_countries` | Top 10 nach Count |
| `hotspot_regions` | Regionen mit ≥3 moderate+ (inkl. max_severity) |
| `trend_anomalies` | Ungewöhnliche Spikes vs. 7-Tage-Ø |
| `last_ingest` | Letzter erfolgreicher IngestRun |

## Regelbasiertes Fallback-Briefing

Implementierung: `backend/app/analysis/rule_briefing.py`, Persistenz via `backend/app/services/briefing_service.py`

```json
{
  "generated_at": "2026-07-13T10:00:00Z",
  "type": "rule_based",
  "overall_risk_score": 42,
  "overall_confidence": "medium",
  "summary": "42 aktive Warnungen weltweit. Global Risk Score: 42/100. Schwerpunkt: Texas, US (5 Warnungen, max. severe).",
  "affected_regions": [
    {"region": "Texas, US", "alert_count": 5, "max_severity": "severe", "alert_ids": ["..."]}
  ],
  "major_events": [
    {"title": "...", "severity": "severe", "source": "noaa", "alert_id": "..."}
  ],
  "cross_border_patterns": [],
  "trend_anomalies": [],
  "potential_implications": {
    "economy": [],
    "logistics": ["Mögliche Beeinträchtigung von Straßen..."],
    "infrastructure": [],
    "technology": [],
    "finance": []
  },
  "limitations": [
    "Regelbasierte Zusammenfassung ohne semantische Interpretation.",
    "Keine wirtschaftlichen Prognosen — nur konservative Hypothesen."
  ],
  "source_alert_ids": ["..."]
}
```

**API:**
- `GET /api/v1/briefings/latest`
- `GET /api/v1/briefings?limit=20&offset=0`
- `POST /api/v1/admin/generate-briefing` (Header `X-Admin-Token`)
- CLI: `python -m app.jobs.cli generate-briefing`

## Konfiguration

| Env-Variable | Default | Beschreibung |
|--------------|---------|--------------|
| `RISK_SCORE_SCALING` | `50` | Normalisierungsfaktor |
| `RISK_CLUSTER_RADIUS_KM` | `100` | Hotspot-Radius |
| `RISK_TREND_WINDOW_DAYS` | `7` | Trend-Fenster |

## Transparenz-Anforderungen

- Score-Zusammensetzung in API `GET /api/v1/stats` als `score_breakdown` exponiert
- Jeder Modifikator mit Begründung und betroffenen Alert-IDs in `alert_details` / `cluster_bonuses`
- Im Dashboard: Tooltip „Wie wird der Score berechnet?“ mit Link zu diesem Dokument

## Nicht-Ziele

- Keine probabilistische Schadensabschätzung
- Keine Versicherungs-/Finanzrisiko-Scores
- Kein Ersatz für behördliche Warnstufen
