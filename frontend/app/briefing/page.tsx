import { getLatestBriefing, getSources, getStats } from "@/lib/api";
import { BriefingView } from "@/components/BriefingView";

export const dynamic = "force-dynamic";

export default async function BriefingPage() {
  const [stats, sourcesResponse] = await Promise.all([getStats(), getSources()]);

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
      <BriefingView briefing={briefing} stats={stats} sources={sourcesResponse.sources} />
    </div>
  );
}
