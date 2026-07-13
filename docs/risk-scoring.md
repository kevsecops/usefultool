# Regelbasierte Risiko-Bewertung (Risk Scoring)

> **Status:** Phase 1 Entwurf — Implementierung in Phase 5  
> **Disclaimer:** Der Score ist ein heuristischer Aggregationsindikator, keine wissenschaftliche Risikobewertung.

## Ziel

Ein transparenter, nachvollziehbarer **Global Risk Score** (0–100) auf Basis normalisierter Warnungen und berechneter Statistiken. Dient als Dashboard-KPI und als Input für regelbasiertes sowie LLM-Briefing.

## Score-Berechnung (Entwurf)

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

### Stufe 3: Regionaler Cluster-Bonus

Wenn in einem **100 km Radius** (oder gleichem Land + Category) ≥3 aktive Warnungen mit `severity >= moderate`:

```
cluster_bonus = count(severe_or_extreme) × 2 + count(moderate) × 1
```

### Stufe 4: Trend-Modifikator

Vergleich aktive Warnungen vs. gleitender 7-Tage-Durchschnitt:

| Verhältnis (aktuell / Ø7d) | Modifikator |
|----------------------------|-------------|
| < 0.8 | ×0.9 (Rückgang) |
| 0.8 – 1.2 | ×1.0 |
| 1.2 – 1.5 | ×1.1 |
| 1.5 – 2.0 | ×1.2 |
| > 2.0 | ×1.3 (ungewöhnliche Häufung) |

### Stufe 5: Aggregation → Global Score

```
raw_total = Σ(alert_score) + Σ(cluster_bonus)
normalized = min(100, round(raw_total / scaling_factor × trend_mod))
```

**`scaling_factor`:** Kalibrierbar via Env `RISK_SCORE_SCALING` (Default: `50`).  
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

Vor Score-Berechnung werden folgende Metriken erzeugt:

| Metrik | Beschreibung |
|--------|--------------|
| `active_count` | Anzahl `is_active=true` |
| `by_country` | Dict `{country_code: count}` |
| `by_category` | Dict `{category: count}` |
| `by_severity` | Dict `{severity: count}` |
| `new_since_last_run` | Neu seit letztem IngestRun |
| `updated_since_last_run` | Geänderte Fingerprints |
| `expired_since_last_run` | Deaktivierte |
| `top_countries` | Top 5 nach Count |
| `hotspot_regions` | Regionen mit ≥3 severe+ |
| `trend_7d` | Aktuell vs. 7-Tage-Ø pro Category |

## Regelbasiertes Fallback-Briefing

Wenn `LLM_ENABLED=false` oder LLM-Validierung fehlschlägt:

```json
{
  "generated_at": "2026-07-13T10:00:00Z",
  "type": "rule_based",
  "overall_risk_score": 42,
  "overall_confidence": "medium",
  "summary": "42 aktive Warnungen weltweit. Schwerpunkt: US (18), DE (5). Höchster Einzelscore: Flood Advisory in Texas.",
  "affected_regions": [
    {"region": "Texas, US", "alert_count": 5, "max_severity": "severe", "alert_ids": ["..."]}
  ],
  "major_events": [
    {"title": "...", "severity": "severe", "source": "noaa", "alert_id": "..."}
  ],
  "limitations": [
    "Regelbasierte Zusammenfassung ohne semantische Interpretation.",
    "Keine wirtschaftlichen Prognosen."
  ],
  "source_alert_ids": ["..."]
}
```

## Konfiguration (geplant)

| Env-Variable | Default | Beschreibung |
|--------------|---------|--------------|
| `RISK_SCORE_SCALING` | `50` | Normalisierungsfaktor |
| `RISK_CLUSTER_RADIUS_KM` | `100` | Hotspot-Radius |
| `RISK_TREND_WINDOW_DAYS` | `7` | Trend-Fenster |

## Transparenz-Anforderungen

- Score-Zusammensetzung in API `GET /api/v1/stats` als `score_breakdown` exponieren
- Jeder Modifikator mit Begründung und betroffenen Alert-IDs
- Im Dashboard: Tooltip „Wie wird der Score berechnet?“ mit Link zu diesem Dokument

## Nicht-Ziele

- Keine probabilistische Schadensabschätzung
- Keine Versicherungs-/Finanzrisiko-Scores
- Kein Ersatz für behördliche Warnstufen
