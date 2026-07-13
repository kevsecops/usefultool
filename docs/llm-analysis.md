# LLM-Analyse — Cross-Alert Intelligence

> **Status:** Phase 2 Architektur (Implementierung Phase 6)  
> **Entscheidung:** LLM ist **Kern-Analyseschicht**, nicht optional für die Produktvision.

## Rolle im System

Das LLM analysiert **Zusammenhänge und Muster zwischen Warnungen** — etwas, was reine Regeln nur begrenzt abbilden können:

- Korrelationen über Quellen hinweg (z. B. GDACS-Erdbeben + NOAA-Tsunami-Warnung in derselben Region)
- Eskalationsketten (mehrere `severe`/`extreme` Alerts in einem Cluster)
- Regionale Hotspots mit kontextueller Einordnung
- Zeitliche Trends und sich verstärkende Muster

**Briefings** (Global Risk Briefing) werden primär LLM-gestützt erzeugt. Regelbasierte Briefings dienen als **Fallback**, wenn das LLM nicht verfügbar ist oder fehlschlägt.

```
Aktive Alerts → Rule-based Stats/Score → LLM Pattern Analysis → Briefing
                              ↓ (LLM fehlt/fehlgeschlagen)
                        Rule-based Briefing (Fallback)
```

## Architektur

| Komponente | Verantwortung |
|------------|---------------|
| `llm/provider.py` | Provider-Abstraktion (Protocol) |
| `llm/openai_compat.py` | OpenAI-kompatible APIs (Prod) |
| `llm/ollama.py` | Lokale Modelle |
| `llm/mock.py` | Deterministische Demo-Antworten |
| `llm/prompts.py` | Prompt-Templates, Output-Schema |
| `analysis/rule_briefing.py` | Fallback ohne LLM |
| `services/briefing_service.py` | Orchestrierung LLM → Fallback |

## Provider-Strategie

| Umgebung | Provider | Konfiguration |
|----------|----------|---------------|
| Demo / Tests | `mock` | `DEMO_MODE=true` oder `LLM_ENABLED=false` |
| Produktion | OpenAI-kompatibel | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` |
| Lokal / Offline | Ollama | `LLM_BASE_URL=http://localhost:11434/v1` |

## Environment-Variablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `LLM_ENABLED` | `true` | `false` deaktiviert LLM (Tests/Demo); Architektur behandelt LLM trotzdem als Kernschicht |
| `LLM_PROVIDER` | `mock` (Demo) / `openai_compat` (Prod) | Aktiver Provider |
| `LLM_BASE_URL` | — | OpenAI-kompatibler Endpoint |
| `LLM_API_KEY` | — | API-Key (nur Backend) |
| `LLM_MODEL` | `gpt-4o-mini` | Modellname |
| `LLM_TIMEOUT_SECONDS` | `30` | Request-Timeout |
| `LLM_MAX_TOKENS` | `2048` | Max. Antwortlänge |

## LLM-Input (anonymisiert)

Nur normalisierte, strukturierte Daten — **kein** `raw_payload`:

```json
{
  "generated_at": "2026-07-13T10:00:00Z",
  "stats": {
    "active_count": 42,
    "global_risk_score": 38,
    "by_country": { "US": 18, "DE": 5 },
    "by_severity": { "severe": 7, "moderate": 15 }
  },
  "alerts": [
    {
      "id": "uuid",
      "source": "gdacs",
      "title": "Earthquake in Papua New Guinea",
      "severity": "severe",
      "category": "earthquake",
      "country_code": "PG",
      "issued_at": "2026-07-13T08:53:27Z"
    }
  ],
  "clusters": [
    { "region": "Texas, US", "count": 5, "max_severity": "severe" }
  ]
}
```

## LLM-Output (validiert)

Strukturiertes JSON — kein rohes HTML:

```json
{
  "overall_assessment": "Elevated risk in US South-Central region...",
  "risk_level": "moderate",
  "confidence": "medium",
  "patterns": [
    {
      "type": "cross_source_correlation",
      "description": "Flood advisories in TX align with GDACS tropical cyclone track",
      "alert_ids": ["uuid1", "uuid2"],
      "severity": "moderate"
    }
  ],
  "hotspots": [
    { "region": "Texas, US", "reason": "5 concurrent severe weather alerts" }
  ],
  "recommendations": [
    "Monitor NOAA flood advisories in Tarrant County"
  ]
}
```

## Fallback-Verhalten

1. `LLM_ENABLED=false` → sofort `rule_based` Briefing
2. LLM-Timeout / HTTP-Fehler → `rule_based` Briefing + Log-Warnung
3. LLM-Output-Validierung fehlgeschlagen → Retry (1×), dann Fallback
4. `IngestRun` / `Briefing.type` = `rule_based` | `llm` für Nachvollziehbarkeit

## Sicherheit

- LLM-Output ist **untrusted** → JSON-Schema-Validierung, keine HTML-Ausgabe
- Keine User-Prompts im MVP (nur System-Prompts)
- Rate-Limiting auf `POST /admin/generate-briefing`
- API-Keys nur serverseitig

Siehe auch: [security.md](./security.md)

## Phasen

| Phase | Inhalt |
|-------|--------|
| 2 | `Briefing`-Modell, Architektur-Dokumentation |
| 5 | Regelbasiertes Fallback-Briefing |
| 6 | LLM-Provider, Prompts, Cross-Alert-Analyse |
