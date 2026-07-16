import type { Category, Severity, AlertSource } from "@/types/alert";

const SEVERITY_COLORS: Record<Severity, string> = {
  minor: "#22c55e",
  moderate: "#eab308",
  severe: "#f97316",
  extreme: "#ef4444",
  unknown: "#6b7280",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  minor: "Gering",
  moderate: "Mittel",
  severe: "Schwer",
  extreme: "Extrem",
  unknown: "Unbekannt",
};

const CATEGORY_LABELS: Record<Category, string> = {
  weather: "Wetter",
  flood: "Hochwasser",
  wildfire: "Waldbrand",
  earthquake: "Erdbeben",
  volcano: "Vulkan",
  tsunami: "Tsunami",
  health: "Gesundheit",
  civil: "Bevölkerungsschutz",
  infrastructure: "Infrastruktur",
  environmental: "Umwelt",
  other: "Sonstiges",
};

const SOURCE_LABELS: Record<AlertSource, string> = {
  nina: "NINA/BBK",
  gdacs: "GDACS",
  noaa: "NOAA/NWS",
};

export function severityColor(severity: Severity): string {
  return SEVERITY_COLORS[severity] ?? SEVERITY_COLORS.unknown;
}

export function severityLabel(severity: Severity): string {
  return SEVERITY_LABELS[severity] ?? severity;
}

export function categoryLabel(category: Category): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function sourceLabel(source: AlertSource): string {
  return SOURCE_LABELS[source] ?? source;
}

export type IngestMode = "live" | "fixture" | "showcase";

export function ingestModeLabel(
  mode: IngestMode | string | undefined | null,
): string {
  if (mode === "showcase") return "Showcase";
  if (mode === "fixture") return "Demo-Daten (Fixture)";
  if (mode === "live") return "Live-Daten";
  return "Unbekannt";
}

export function ingestModeBadgeClass(
  mode: IngestMode | string | undefined | null,
): string {
  if (mode === "showcase") return "bg-violet-100 text-violet-800";
  if (mode === "fixture") return "bg-amber-100 text-amber-800";
  return "bg-emerald-100 text-emerald-800";
}

export function sourceHealthLabel(healthy: boolean): string {
  return healthy ? "Erreichbar" : "Nicht erreichbar";
}

export function sourceHealthBadgeClass(healthy: boolean): string {
  return healthy ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800";
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "gerade eben";
  if (diffMin < 60) return `vor ${diffMin} Min.`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `vor ${diffHours} Std.`;
  const diffDays = Math.floor(diffHours / 24);
  return `vor ${diffDays} Tag${diffDays === 1 ? "" : "en"}`;
}

export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trimEnd()}…`;
}
