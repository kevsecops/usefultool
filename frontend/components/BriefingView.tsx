import type { Stats } from "@/types/stats";
import { categoryLabel, formatDateTime } from "@/lib/format";

interface BriefingViewProps {
  stats: Stats;
}

export function BriefingView({ stats }: BriefingViewProps) {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <h2 className="font-semibold text-amber-900">
          Briefing — Phase 5–6
        </h2>
        <p className="mt-1 text-sm text-amber-800">
          Das LLM-gestützte Global Risk Briefing mit Cross-Alert-Musteranalyse
          folgt in Phase 5–6. Bis dahin zeigen wir eine Zusammenfassung der
          aktuellen Statistiken.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Aktive Warnungen" value={stats.active_count} />
        <StatCard
          label="Global Risk Score"
          value={stats.global_risk_score}
        />
        <StatCard
          label="Länder betroffen"
          value={Object.keys(stats.by_country).length}
        />
        <StatCard
          label="Letztes Update"
          value={formatDateTime(stats.last_ingest)}
          isText
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Nach Kategorie</h3>
          <ul className="space-y-2">
            {Object.entries(stats.by_category)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, count]) => (
                <li
                  key={cat}
                  className="flex items-center justify-between text-sm"
                >
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
                <li
                  key={sev}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="capitalize text-slate-700">{sev}</span>
                  <span className="font-medium text-slate-900">{count}</span>
                </li>
              ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  isText = false,
}: {
  label: string;
  value: number | string;
  isText?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p
        className={`mt-1 font-bold text-slate-900 ${isText ? "text-lg" : "text-3xl"}`}
      >
        {value}
      </p>
    </div>
  );
}
