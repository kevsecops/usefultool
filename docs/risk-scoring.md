# Global Risk Score v2

> **Status:** Phase 8 — multi-factor scoring  
> **Disclaimer:** The score is a heuristic aggregation indicator, not a scientific risk assessment.

## Goal

A transparent, explainable **Global Risk Score** (0–100) that reflects **event severity, infrastructure exposure, and corroborated impact signals** — not raw alert count. Used as a dashboard KPI and input for rule-based and LLM briefings.

**Implementation:** `backend/app/analysis/risk_score.py` (version `2`)

## Why v2?

The v1 model summed per-alert weights and cluster bonuses, then scaled by active alert count. With dozens of live NOAA/NWS warnings worldwide, `raw_total` routinely exceeded the normalization ceiling and the score **saturated at 100** regardless of actual impact.

v2 replaces alert-count scaling with four capped factors derived from canonical events, asset exposures, multi-source corroboration, and implication evidence.

## Score Formula (v2)

```
global_score = min(100,
    event_severity_index          (0–40)
  + infrastructure_exposure_index (0–30)
  + multi_source_corroboration    (0–15)
  + humanitarian_impact_signal    (0–15)
)
```

Each factor uses **diminishing returns** so additional events/assets add progressively less — preventing saturation from volume alone.

### Factor 1: Event Severity Index (0–40)

**Primary source:** active canonical events (`severity` + `confidence`).

| Severity | Weight |
|----------|--------|
| `minor` | 2 |
| `moderate` | 6 |
| `severe` | 12 |
| `extreme` | 20 |

| Confidence | Multiplier |
|------------|------------|
| `low` | ×0.7 |
| `medium` | ×1.0 |
| `high` | ×1.2 |

Per-event contribution = `severity_weight × confidence_mod`. Contributions are sorted descending and summed with exponential decay (`0.65^rank`). Result is scaled to 0–40 (reference max ≈ 28 raw).

**Alert fallback:** When no canonical events exist, only the **top 5 alerts** by severity contribute, using reduced weights (severe=5, extreme=8, etc.). This prevents hundreds of minor weather advisories from dominating the score.

### Factor 2: Infrastructure Exposure Index (0–30)

Based on `event_asset_exposures` for active canonical events, deduplicated per asset (highest score wins).

| Asset type | Weight |
|------------|--------|
| `port` | 3 |
| `airport` | 2 |
| `power_plant` | 4 |

| Importance | Multiplier |
|------------|------------|
| `low` | ×0.5 |
| `medium` | ×1.0 |
| `high` | ×1.5 |
| `critical` | ×2.0 |

| Exposure type | Multiplier |
|---------------|------------|
| `inside_event_area` / overlap | ×1.0 |
| `near_event_area` | ×0.5 |
| `system_level_exposure` | ×0.7 |

```
asset_score = type_weight × importance_mod × overlap_mod × confidence_mod
```

Diminishing sum (decay 0.6) → scaled to 0–30.

### Factor 3: Multi-Source Corroboration (0–15)

For each active canonical event with **≥2 linked sources** (alerts, observed events):

```
bonus = min(5, (source_count − 1) × 2)
```

Summed across corroborated events, capped at 15.

### Factor 4: Humanitarian / Impact Signal (0–15)

From `implication_candidates` with qualifying evidence:

| Evidence level | Weight |
|----------------|--------|
| `officially_reported` | 5 |
| `observed` | 4 |
| `inferred_from_exposure` | 3 |
| `hypothesis` | 0 (excluded) |

Multiplied by confidence modifier and a 1.5× boost for `humanitarian`, `public_health`, `infrastructure`, `energy` categories. Diminishing sum → scaled to 0–15.

## Score Interpretation (UI)

| Range | Label | Color |
|-------|-------|-------|
| 0–20 | Low | Green |
| 21–40 | Moderate | Yellow |
| 41–60 | Elevated | Orange |
| 61–80 | High | Red |
| 81–100 | Critical | Dark red |

## Expected Ranges

| Scenario | Typical score |
|----------|---------------|
| No active events | 0 |
| Many minor live alerts, no canonical events | 5–20 |
| Showcase (3 events + exposures + corroboration) | 40–70 |
| Extreme multi-source crisis with critical exposures | 80–100 (rare) |

## API

`GET /api/v1/stats` returns:

| Field | Description |
|-------|-------------|
| `global_risk_score` | Normalized score 0–100 |
| `score_breakdown` | v2 breakdown with `version: "2"`, per-factor details |
| `canonical_event_count` | Active canonical events used in scoring |

### Breakdown structure

```json
{
  "version": "2",
  "factor_totals": {
    "event_severity": 28,
    "infrastructure_exposure": 18,
    "multi_source_corroboration": 6,
    "humanitarian_impact": 8
  },
  "event_severity_index": { "source": "canonical_events", "index": 28, ... },
  "infrastructure_exposure_index": { "unique_assets": 3, "index": 18, ... },
  "multi_source_corroboration": { "corroborated_events": 1, "index": 6, ... },
  "humanitarian_impact_signal": { "qualifying_implications": 2, "index": 8, ... }
}
```

## Data Loading

`backend/app/services/risk_score_service.py` → `gather_risk_inputs(db, alerts)` loads:

- Active canonical events (with links)
- Event–asset exposures for those events (with asset details)
- All implication candidates

Used by `stats_service` and `briefing_service`.

## Briefing Integration

Rule-based briefing summaries include factor breakdown:

> Global Risk Score: 52/100 (Schwere: 28, Infrastruktur: 18, Quellen: 6, Auswirkung: 8).

## v1 → v2 Migration Notes

Removed from scoring (still computed for stats display):

- Per-alert linear summation
- Regional cluster bonuses
- Trend modifier on alert count

`RISK_SCORE_SCALING` env var is **no longer used** in v2.

## Transparency Requirements

- Full `score_breakdown` in `GET /api/v1/stats`
- Dashboard tooltip linking to this document
- Each factor exposes top contributing events/assets/implications

## Non-Goals

- No population-weighted regional impact (no population dataset yet)
- No probabilistic damage modeling
- No insurance/financial risk scores
- Not a replacement for official warning levels
