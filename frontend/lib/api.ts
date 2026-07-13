import type { AlertFilters, AlertListResponse } from "@/types/alert";
import type { Stats } from "@/types/stats";
import type { SourcesResponse } from "@/types/source";
import type { Alert } from "@/types/alert";
import type { Briefing, BriefingListResponse } from "@/types/briefing";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getBaseUrl(): string {
  if (typeof window === "undefined") {
    return (
      process.env.API_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000"
    );
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
    next: { revalidate: 30 },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export async function getHealth(): Promise<{ status: string; demo_mode: boolean }> {
  return apiFetch("/health");
}

export async function getAlerts(filters: AlertFilters = {}): Promise<AlertListResponse> {
  const query = buildQuery({
    source: filters.source,
    country: filters.country,
    category: filters.category,
    severity: filters.severity,
    active: filters.active ?? true,
    issued_after: filters.issued_after,
    issued_before: filters.issued_before,
    bounding_box: filters.bounding_box,
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0,
  });
  return apiFetch(`/api/v1/alerts${query}`);
}

export async function getAlert(id: string): Promise<Alert> {
  return apiFetch(`/api/v1/alerts/${id}`);
}

export async function getStats(): Promise<Stats> {
  return apiFetch("/api/v1/stats");
}

export async function getSources(): Promise<SourcesResponse> {
  return apiFetch("/api/v1/sources");
}

export async function getLatestBriefing(): Promise<Briefing> {
  return apiFetch("/api/v1/briefings/latest");
}

export async function getBriefings(
  limit = 20,
  offset = 0,
): Promise<BriefingListResponse> {
  return apiFetch(`/api/v1/briefings?limit=${limit}&offset=${offset}`);
}
