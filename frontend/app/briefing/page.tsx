import { getHealth, getLatestBriefing, getSources, getStats } from "@/lib/api";
import { BriefingView } from "@/components/BriefingView";
import type { Stats } from "@/types/stats";
import type { SourceInfo } from "@/types/source";

export const dynamic = "force-dynamic";

const EMPTY_STATS: Stats = {
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

export default async function BriefingPage() {
  let stats = EMPTY_STATS;
  let sources: SourceInfo[] = [];
  let demoMode = false;
  let showcaseMode = false;
  let error: string | null = null;

  try {
    const [statsResponse, sourcesResponse, health] = await Promise.all([
      getStats(),
      getSources(),
      getHealth(),
    ]);
    stats = statsResponse;
    sources = sourcesResponse.sources;
    demoMode = health.demo_mode;
    showcaseMode = health.showcase_mode ?? false;
  } catch (e) {
    error = e instanceof Error ? e.message : "API nicht erreichbar";
  }

  let briefing = null;
  try {
    briefing = await getLatestBriefing();
  } catch {
    // No briefing generated yet — BriefingView shows fallback
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Briefing</h1>
        <p className="mt-1 text-slate-600">
          Globale Risikoanalyse und Zusammenfassung.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Backend nicht erreichbar: {error}. Stellen Sie sicher, dass die API
          unter {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}{" "}
          läuft und Daten ingestiert wurden.
        </div>
      )}

      <BriefingView
        briefing={briefing}
        stats={stats}
        sources={sources}
        demoMode={demoMode}
        showcaseMode={showcaseMode}
      />
    </div>
  );
}
