import type { AlertFilters, AlertSource, Category, Severity } from "@/types/alert";

export function filtersFromSearchParams(
  searchParams: Record<string, string | string[] | undefined>,
  defaults: Partial<AlertFilters> = {},
): AlertFilters {
  const get = (key: string) => {
    const v = searchParams[key];
    return Array.isArray(v) ? v[0] : v;
  };

  const page = Math.max(1, parseInt(get("page") ?? "1", 10) || 1);
  const limit = defaults.limit ?? 20;
  const offset = defaults.offset ?? (page - 1) * limit;

  return {
    source: (get("source") as AlertSource) || undefined,
    country: get("country") || undefined,
    category: (get("category") as Category) || undefined,
    severity: (get("severity") as Severity) || undefined,
    active: get("active") !== "false",
    limit,
    offset,
  };
}
