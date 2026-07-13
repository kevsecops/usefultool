import type { Briefing } from "@/types/briefing";
import type { Stats } from "@/types/stats";
import { categoryLabel, formatDateTime } from "@/lib/format";
import Link from "next/link";

interface BriefingViewProps {
  briefing: Briefing | null;
  stats: Stats;
}

const CONFIDENCE_LABELS: Record<string, string> = {
  low: "Niedrig",
  medium: "Mittel",
  high: "Hoch",
};

export function BriefingView({ briefing, stats }: BriefingViewProps) {
  if (!briefing) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h2 className="font-semibold text-amber-900">Kein Briefing verfügbar</h2>
          <p className="mt-1 text-sm text-amber-800">
            Es wurde noch kein Briefing generiert. Führen Sie einen Ingest mit{" "}
            <code className="rounded bg-amber-100 px-1">generate_briefing: true</code>{" "}
            aus oder nutzen Sie{" "}
            <code className="rounded bg-amber-100 px-1">python -m app.jobs.cli generate-briefing</code>.
          </p>
        </div>
        <StatsFallback stats={stats} />
      </div>
    );
  }

  const content = briefing.content;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-slate-500">
              {briefing.type === "rule_based" ? "Regelbasiertes Briefing" : "LLM-Briefing"}
              {" · "}
              Vertrauen: {CONFIDENCE_LABELS[briefing.overall_confidence] ?? briefing.overall_confidence}
            </p>
            <p className="mt-2 text-lg text-slate-800">{content.summary}</p>
          </div>
          <div className="text-right text-sm text-slate-500">
            <p>{formatDateTime(briefing.generated_at)}</p>
            <p className="mt-1 font-semibold text-slate-900">
              Risk Score: {briefing.overall_risk_score}/100
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Aktive Warnungen" value={stats.active_count} />
        <StatCard label="Global Risk Score" value={briefing.overall_risk_score} />
        <StatCard
          label="Betroffene Regionen"
          value={content.affected_regions.length}
        />
        <StatCard
          label="Quell-Warnungen"
          value={content.source_alert_ids.length}
        />
      </div>

      {content.affected_regions.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Betroffene Regionen</h3>
          <ul className="space-y-2">
            {content.affected_regions.map((r) => (
              <li
                key={r.region}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-slate-700">
                  {r.region}{" "}
                  <span className="text-slate-400">({r.max_severity})</span>
                </span>
                <span className="font-medium text-slate-900">{r.alert_count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.major_events.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Wesentliche Ereignisse</h3>
          <ul className="space-y-3">
            {content.major_events.map((event) => (
              <li key={event.alert_id} className="text-sm">
                <Link
                  href={`/alerts/${event.alert_id}`}
                  className="font-medium text-blue-700 hover:underline"
                >
                  {event.title}
                </Link>
                <p className="text-slate-500">
                  {event.severity} · {event.source}
                  {event.region ? ` · ${event.region}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.cross_border_patterns.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Muster (Beobachtungen)</h3>
          <ul className="space-y-2">
            {content.cross_border_patterns.map((p, i) => (
              <li key={i} className="text-sm text-slate-700">
                {p.description}
                <span className="ml-2 text-xs text-slate-400">
                  ({p.confidence})
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.trend_anomalies.length > 0 && (
        <section className="rounded-lg border border-orange-200 bg-orange-50 p-4">
          <h3 className="mb-3 font-semibold text-orange-900">Trend-Anomalien</h3>
          <ul className="space-y-2">
            {content.trend_anomalies.map((a) => (
              <li key={`${a.dimension}-${a.key}`} className="text-sm text-orange-800">
                {a.dimension === "global"
                  ? "Global"
                  : `${a.dimension}: ${a.key}`}
                : {a.current_count} aktiv (Ø7d: {a.rolling_avg}, Faktor: {a.ratio}×)
              </li>
            ))}
          </ul>
        </section>
      )}

      <ImplicationsSection implications={content.potential_implications} />

      {content.limitations.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <h3 className="mb-2 font-semibold text-slate-700">Einschränkungen</h3>
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
            {content.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="rounded-lg border border-slate-200 bg-slate-100 p-4 text-sm text-slate-600">
        <strong>Disclaimer:</strong> Regelbasierte Zusammenfassung aus öffentlichen
        Warnmeldungen — keine amtlichen Bewertungen. Implikationen sind konservative
        Hypothesen, keine Prognosen.
      </div>
    </div>
  );
}

function ImplicationsSection({
  implications,
}: {
  implications: Briefing["content"]["potential_implications"];
}) {
  const domains = [
    { key: "economy" as const, label: "Wirtschaft" },
    { key: "logistics" as const, label: "Logistik" },
    { key: "infrastructure" as const, label: "Infrastruktur" },
    { key: "technology" as const, label: "Technologie" },
    { key: "finance" as const, label: "Finanzen" },
  ];
  const hasAny = domains.some((d) => implications[d.key].length > 0);
  if (!hasAny) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-1 font-semibold text-slate-900">
        Mögliche Implikationen (Hypothesen)
      </h3>
      <p className="mb-3 text-xs text-slate-500">
        Konservative Ableitungen aus Kategorien — keine verifizierten Auswirkungen.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {domains.map(
          (d) =>
            implications[d.key].length > 0 && (
              <div key={d.key}>
                <h4 className="text-sm font-medium text-slate-800">{d.label}</h4>
                <ul className="mt-1 list-inside list-disc text-sm text-slate-600">
                  {implications[d.key].map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            ),
        )}
      </div>
    </section>
  );
}

function StatsFallback({ stats }: { stats: Stats }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-slate-900">Nach Kategorie</h3>
        <ul className="space-y-2">
          {Object.entries(stats.by_category)
            .sort(([, a], [, b]) => b - a)
            .map(([cat, count]) => (
              <li key={cat} className="flex items-center justify-between text-sm">
                <span className="text-slate-700">
                  {categoryLabel(cat as Parameters<typeof categoryLabel>[0])}
                </span>
                <span className="font-medium text-slate-900">{count}</span>
              </li>
            ))}
        </ul>
      </section>
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-slate-900">Nach Schweregrad</h3>
        <ul className="space-y-2">
          {Object.entries(stats.by_severity)
            .sort(([, a], [, b]) => b - a)
            .map(([sev, count]) => (
              <li key={sev} className="flex items-center justify-between text-sm">
                <span className="capitalize text-slate-700">{sev}</span>
                <span className="font-medium text-slate-900">{count}</span>
              </li>
            ))}
        </ul>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
