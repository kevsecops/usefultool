import { getAlerts, getHealth, getStats } from "@/lib/api";
import { RiskScoreGauge } from "@/components/RiskScoreGauge";
import { AlertCard } from "@/components/AlertCard";
import { formatDateTime, formatRelativeTime, sourceLabel } from "@/lib/format";
import type { AlertSource } from "@/types/alert";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let stats;
  let recentAlerts;
  let health;
  let error: string | null = null;

  try {
    [stats, recentAlerts, health] = await Promise.all([
      getStats(),
      getAlerts({ limit: 5, active: true }),
      getHealth(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "API nicht erreichbar";
    health = null;
    stats = {
      active_count: 0,
      global_risk_score: 0,
      score_breakdown: {},
      by_country: {},
      by_category: {},
      by_severity: {},
      by_source: {},
      top_countries: [],
      hotspot_regions: [],
      trend_anomalies: [],
      last_ingest: null,
    };
    recentAlerts = { items: [], total: 0, limit: 5, offset: 0 };
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Startseite</h1>
        <p className="mt-1 text-slate-600">
          Globale Risikoübersicht aus aggregierten öffentlichen Warnmeldungen.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Backend nicht erreichbar: {error}. Stellen Sie sicher, dass die API
          unter {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}{" "}
          läuft und Daten ingestiert wurden.
        </div>
      )}

      {!error && health?.showcase_mode && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm text-violet-900">
          <p className="font-medium">Showcase / Demo-Modus aktiv</p>
          <p className="mt-1">
            Angezeigte Daten stammen aus kuratierten Demoszenarien — keine externen
            API-Schlüssel erforderlich.{" "}
            <code className="rounded bg-violet-100 px-1">SHOWCASE_MODE=true</code>
          </p>
        </div>
      )}

      {!error && health?.status === "degraded" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-medium">Daten-Pipeline beeinträchtigt</p>
          <p className="mt-1">
            {health.last_ingest_error
              ? `Letzter Ingest-Fehler: ${health.last_ingest_error.slice(0, 240)}${health.last_ingest_error.length > 240 ? "…" : ""}`
              : "Der letzte Ingest-Lauf war nicht vollständig erfolgreich."}{" "}
            Das Dashboard zeigt ggf. keine aktuellen Warnungen, bis der nächste
            Ingest erfolgreich war.
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex items-center justify-center rounded-lg border border-slate-200 bg-white p-6 lg:col-span-1">
          <RiskScoreGauge score={stats.global_risk_score} />
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">Aktive Warnungen</p>
            <p className="text-3xl font-bold text-slate-900">
              {stats.active_count}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">Letztes Update</p>
            <p className="text-lg font-semibold text-slate-900">
              {stats.last_ingest
                ? formatRelativeTime(stats.last_ingest)
                : "—"}
            </p>
            {stats.last_ingest && (
              <p className="text-xs text-slate-400">
                {formatDateTime(stats.last_ingest)}
              </p>
            )}
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">Canonical Events</p>
            <p className="text-3xl font-bold text-slate-900">
              {stats.canonical_event_count ?? health?.canonical_event_count ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">Observed Events</p>
            <p className="text-3xl font-bold text-slate-900">
              {stats.observed_event_count ?? health?.active_observed_event_count ?? 0}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-semibold text-slate-900">
            Top betroffene Regionen
          </h2>
          {stats.hotspot_regions.length > 0 ? (
            <ul className="space-y-2">
              {stats.hotspot_regions.map((r) => (
                <li
                  key={r.region}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-slate-700">{r.region}</span>
                  <span className="font-medium text-slate-900">{r.count}</span>
                </li>
              ))}
            </ul>
          ) : stats.top_countries.length > 0 ? (
            <ul className="space-y-2">
              {stats.top_countries.map((c) => (
                <li
                  key={c.code}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-slate-700">{c.code}</span>
                  <span className="font-medium text-slate-900">{c.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">Keine Daten verfügbar.</p>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-semibold text-slate-900">Nach Datenquelle</h2>
          {Object.keys(stats.by_source ?? {}).length > 0 ? (
            <ul className="space-y-2">
              {Object.entries(stats.by_source)
                .sort(([, a], [, b]) => b - a)
                .map(([src, count]) => (
                  <li
                    key={src}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-slate-700">
                      {sourceLabel(src as AlertSource)}
                    </span>
                    <span className="font-medium text-slate-900">{count}</span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">Keine Daten verfügbar.</p>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-semibold text-slate-900">Zusammenfassung</h2>
          <p className="text-sm text-slate-600">
            {stats.active_count > 0
              ? `Derzeit ${stats.active_count} aktive Warnung${stats.active_count === 1 ? "" : "en"} aus ${Object.keys(stats.by_country).length || "mehreren"} Ländern. Der Global Risk Score liegt bei ${stats.global_risk_score}/100.`
              : "Noch keine aktiven Warnungen erfasst. Führen Sie einen Ingest aus, um Demo-Daten zu laden."}
          </p>
          {Object.keys(stats.by_severity).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(stats.by_severity).map(([sev, count]) => (
                <span
                  key={sev}
                  className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700"
                >
                  {sev}: {count}
                </span>
              ))}
            </div>
          )}
        </section>
      </div>

      {recentAlerts.items.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-slate-900">
            Neueste Warnungen
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recentAlerts.items.map((alert) => (
              <AlertCard key={alert.id} alert={alert} compact />
            ))}
          </div>
        </section>
      )}

      <div className="rounded-lg border border-slate-200 bg-slate-100 p-4 text-sm text-slate-600">
        <strong>Disclaimer:</strong> Aggregated public warnings — not official
        alerts. Dieses Dashboard aggregiert öffentlich zugängliche Meldungen und
        stellt keine amtlichen Warnungen dar.
      </div>
    </div>
  );
}
