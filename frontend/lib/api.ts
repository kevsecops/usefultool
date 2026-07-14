import type { AlertFilters, AlertListResponse } from "@/types/alert";
import type { Stats } from "@/types/stats";
import type { SourcesResponse } from "@/types/source";
import type { Alert } from "@/types/alert";
import type { Briefing, BriefingListResponse } from "@/types/briefing";
import type {
  CanonicalEvent,
  CanonicalEventListResponse,
  EventImplicationsResponse,
  EventSourcesResponse,
  FireClustersResponse,
  ObservedEventListResponse,
  SpaceWeatherResponse,
} from "@/types/events";
import type { AssetListResponse, EventExposureListResponse } from "@/types/exposure";

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

export async function getHealth(): Promise<{
  status: string;
  demo_mode: boolean;
  showcase_mode?: boolean;
  ingest_mode?: string;
  last_ingest_error?: string | null;
  canonical_event_count?: number;
  active_observed_event_count?: number;
}> {
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

export async function getObservedEvents(
  params: {
    source?: string;
    category?: string;
    severity?: string;
    active?: boolean;
    bounding_box?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<ObservedEventListResponse> {
  const query = buildQuery({
    source: params.source,
    category: params.category,
    severity: params.severity,
    active: params.active ?? true,
    bounding_box: params.bounding_box,
    limit: params.limit ?? 100,
    offset: params.offset ?? 0,
  });
  return apiFetch(`/api/v1/observed-events${query}`);
}

export async function getCanonicalEvents(
  params: {
    event_type?: string;
    severity?: string;
    status?: string;
    active?: boolean;
    bounding_box?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<CanonicalEventListResponse> {
  const query = buildQuery({
    event_type: params.event_type,
    severity: params.severity,
    status: params.status,
    active: params.active ?? true,
    bounding_box: params.bounding_box,
    limit: params.limit ?? 100,
    offset: params.offset ?? 0,
  });
  return apiFetch(`/api/v1/events${query}`);
}

export async function getEvent(id: string): Promise<CanonicalEvent> {
  return apiFetch(`/api/v1/events/${id}`);
}

export async function getEventSources(id: string): Promise<EventSourcesResponse> {
  return apiFetch(`/api/v1/events/${id}/sources`);
}

export async function getEventExposures(id: string): Promise<EventExposureListResponse> {
  return apiFetch(`/api/v1/events/${id}/exposures`);
}

export async function getEventImplications(id: string): Promise<EventImplicationsResponse> {
  return apiFetch(`/api/v1/events/${id}/implications`);
}

export async function getAssets(
  params: {
    asset_type?: string;
    country_code?: string;
    bounding_box?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AssetListResponse> {
  const query = buildQuery({
    asset_type: params.asset_type,
    country_code: params.country_code,
    bounding_box: params.bounding_box,
    limit: params.limit ?? 200,
    offset: params.offset ?? 0,
  });
  return apiFetch(`/api/v1/assets${query}`);
}

export async function getFireClusters(
  params: { active?: boolean; limit?: number } = {},
): Promise<FireClustersResponse> {
  const query = buildQuery({
    active: params.active ?? true,
    limit: params.limit ?? 50,
  });
  return apiFetch(`/api/v1/fire-clusters${query}`);
}

export async function getSpaceWeather(
  params: { active?: boolean; limit?: number } = {},
): Promise<SpaceWeatherResponse> {
  const query = buildQuery({
    active: params.active ?? true,
    limit: params.limit ?? 50,
  });
  return apiFetch(`/api/v1/space-weather${query}`);
}
