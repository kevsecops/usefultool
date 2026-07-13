import type { BriefingContent, SourceCount } from "@/types/briefing";
import type { Stats } from "@/types/stats";
import { sourceLabel } from "@/lib/format";
import type { AlertSource } from "@/types/alert";

const SOURCE_LABELS: Record<string, string> = {
  nina: "NINA/BBK",
  gdacs: "GDACS",
  noaa: "NOAA/NWS",
};

export type BySourceResolution =
  | { items: SourceCount[]; derived: false }
  | { items: SourceCount[]; derived: true; reason: "major_events" | "live_stats" };

function normalizeBySource(raw: BriefingContent["by_source"] | Record<string, number> | undefined): SourceCount[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .filter((item) => item?.source && item.count > 0)
      .map((item) => ({
        source: item.source,
        label: item.label || SOURCE_LABELS[item.source] || item.source,
        count: item.count,
      }));
  }
  if (typeof raw === "object") {
    return Object.entries(raw)
      .filter(([, count]) => count > 0)
      .map(([source, count]) => ({
        source,
        label: SOURCE_LABELS[source] || source,
        count,
      }))
      .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));
  }
  return [];
}

function deriveFromMajorEvents(content: BriefingContent): SourceCount[] {
  const counts = new Map<string, number>();
  for (const event of content.major_events ?? []) {
    if (event.source) {
      counts.set(event.source, (counts.get(event.source) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([source, count]) => ({
      source,
      label: SOURCE_LABELS[source] || sourceLabel(source as AlertSource),
      count,
    }))
    .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));
}

function deriveFromLiveStats(stats: Stats): SourceCount[] {
  return Object.entries(stats.by_source ?? {})
    .filter(([, count]) => count > 0)
    .map(([source, count]) => ({
      source,
      label: SOURCE_LABELS[source] || sourceLabel(source as AlertSource),
      count,
    }))
    .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));
}

export function resolveBySource(
  content: BriefingContent,
  stats?: Stats,
): BySourceResolution {
  const snapshot = normalizeBySource(content.by_source);
  if (snapshot.length > 0) {
    return { items: snapshot, derived: false };
  }

  const hasAlerts =
    content.active_count > 0 ||
    (content.source_alert_ids?.length ?? 0) > 0 ||
    (content.major_events?.length ?? 0) > 0;

  if (!hasAlerts) {
    return { items: [], derived: false };
  }

  const fromEvents = deriveFromMajorEvents(content);
  if (fromEvents.length > 0) {
    return { items: fromEvents, derived: true, reason: "major_events" };
  }

  const fromStats = stats ? deriveFromLiveStats(stats) : [];
  if (fromStats.length > 0) {
    return { items: fromStats, derived: true, reason: "live_stats" };
  }

  return { items: [], derived: false };
}

export function distinctSourceCount(resolution: BySourceResolution): number | "—" {
  if (resolution.items.length > 0) {
    return resolution.items.length;
  }
  return "—";
}
