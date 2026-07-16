import type {
  AffectedRegion,
  BriefingContent,
  CrossBorderPattern,
  ObservedEventItem,
  ObservedEventsSection,
  PotentialImplications,
  SourceCount,
  VerifiedExposureItem,
  VerifiedExposureSection,
} from "@/types/briefing";
import type { Stats } from "@/types/stats";
import { sourceLabel } from "@/lib/format";
import type { AlertSource } from "@/types/alert";

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeSection<T>(
  value: unknown,
  fallback: { summary: string; items: T[]; confidence: string },
  normalizeItem: (item: unknown) => T,
): { summary: string; items: T[]; confidence: string } {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return fallback;
  }
  const section = value as Record<string, unknown>;
  return {
    summary: asString(section.summary, fallback.summary),
    items: asArray<unknown>(section.items).map(normalizeItem),
    confidence: asString(section.confidence, fallback.confidence),
  };
}

function normalizeObservedEventItem(item: unknown): ObservedEventItem {
  const raw = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
  return {
    canonical_event_id: asString(raw.canonical_event_id ?? raw.event_id),
    event_title: asString(raw.event_title ?? raw.title, "Unbekanntes Ereignis"),
    event_type: raw.event_type != null ? asString(raw.event_type) : undefined,
    severity: asString(raw.severity, "unknown"),
    observed_count: asNumber(raw.observed_count),
    sources: asArray<string>(raw.sources),
    source_ids: asArray<string>(raw.source_ids),
  };
}

function normalizeVerifiedExposureItem(item: unknown): VerifiedExposureItem {
  const raw = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
  return {
    event_id: asString(raw.event_id),
    event_title: asString(raw.event_title, "Unbekanntes Ereignis"),
    asset_name: asString(raw.asset_name, "Unbekannt"),
    asset_type: asString(raw.asset_type, "unknown"),
    exposure_type: asString(raw.exposure_type, "unknown"),
    confidence: asString(raw.confidence, "medium"),
    source_ids: asArray<string>(raw.source_ids),
  };
}

function normalizePotentialImplications(value: unknown): PotentialImplications {
  const empty: PotentialImplications = {
    economy: [],
    logistics: [],
    infrastructure: [],
    technology: [],
    finance: [],
  };
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return empty;
  }
  const raw = value as Record<string, unknown>;
  return {
    economy: asArray<string>(raw.economy),
    logistics: asArray<string>(raw.logistics),
    infrastructure: asArray<string>(raw.infrastructure),
    technology: asArray<string>(raw.technology),
    finance: asArray<string>(raw.finance),
  };
}

const EMPTY_OBSERVED_EVENTS: ObservedEventsSection = {
  summary: "",
  items: [],
  confidence: "low",
};

const EMPTY_VERIFIED_EXPOSURE: VerifiedExposureSection = {
  summary: "",
  items: [],
  confidence: "low",
};

/** Coerce LLM briefing snapshots to the shape BriefingView expects. */
export function normalizeBriefingContent(content: BriefingContent): BriefingContent {
  return {
    ...content,
    by_source: asArray(content.by_source),
    top_countries: asArray(content.top_countries),
    affected_regions: asArray<AffectedRegion>(content.affected_regions).map((region) => ({
      region: asString(region?.region),
      alert_count: asNumber(region?.alert_count),
      max_severity: asString(region?.max_severity, "unknown"),
      alert_ids: asArray<string>(region?.alert_ids),
    })),
    major_events: asArray(content.major_events),
    cross_border_patterns: asArray<CrossBorderPattern>(content.cross_border_patterns).map(
      (pattern) => ({
        type: asString(pattern?.type, "unknown"),
        description: asString(pattern?.description),
        alert_ids: asArray<string>(pattern?.alert_ids),
        confidence: asString(pattern?.confidence, "low"),
      }),
    ),
    trend_anomalies: asArray(content.trend_anomalies),
    potential_implications: normalizePotentialImplications(content.potential_implications),
    observed_events: normalizeSection(
      content.observed_events,
      EMPTY_OBSERVED_EVENTS,
      normalizeObservedEventItem,
    ),
    verified_exposure: normalizeSection(
      content.verified_exposure,
      EMPTY_VERIFIED_EXPOSURE,
      normalizeVerifiedExposureItem,
    ),
    evidence_gaps: asArray(content.evidence_gaps),
    limitations: asArray(content.limitations),
    source_alert_ids: asArray(content.source_alert_ids),
    confirmed_impacts: asArray(content.confirmed_impacts),
    cross_border_relevance: asArray(content.cross_border_relevance),
    technology_infrastructure_risks: asArray(content.technology_infrastructure_risks),
  };
}

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
