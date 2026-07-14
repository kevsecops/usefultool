export type AlertSource = "nina" | "gdacs" | "noaa";

/** Observed-event sources (Phase 1–2); not used for alert filters yet. */
export type ObservedEventSource = "usgs" | "eonet" | "noaa_swpc";

export type DataSource = AlertSource | ObservedEventSource;

export type SpatialScope =
  | "local"
  | "regional"
  | "continental"
  | "global"
  | "orbital";

export type Severity = "unknown" | "minor" | "moderate" | "severe" | "extreme";

export type Urgency =
  | "immediate"
  | "expected"
  | "future"
  | "past"
  | "unknown";

export type Certainty =
  | "observed"
  | "likely"
  | "possible"
  | "unlikely"
  | "unknown";

export type Category =
  | "weather"
  | "flood"
  | "wildfire"
  | "earthquake"
  | "volcano"
  | "tsunami"
  | "health"
  | "civil"
  | "infrastructure"
  | "environmental"
  | "other";

export type AlertStatus = "actual" | "exercise" | "test" | "draft" | "unknown";

export interface Alert {
  id: string;
  source: AlertSource;
  source_alert_id: string;
  source_url: string | null;
  title: string;
  description: string | null;
  instruction: string | null;
  country_code: string | null;
  country_name: string | null;
  region: string | null;
  location_name: string | null;
  latitude: number | null;
  longitude: number | null;
  geometry: GeoJSON.Geometry | null;
  category: Category;
  event_type: string | null;
  severity: Severity;
  urgency: Urgency | null;
  certainty: Certainty | null;
  status: AlertStatus;
  language: string | null;
  issued_at: string;
  effective_at: string | null;
  starts_at: string | null;
  expires_at: string | null;
  updated_at_source: string | null;
  ingested_at: string;
  last_seen_at: string;
  raw_payload?: Record<string, unknown> | null;
  fingerprint: string;
  is_active: boolean;
  ingest_mode?: "live" | "fixture" | "showcase";
}

export interface ObservedEvent {
  id: string;
  source: ObservedEventSource;
  source_event_id: string;
  source_url: string | null;
  title: string;
  description: string | null;
  event_type: string | null;
  category: Category;
  severity: Severity;
  status: string;
  confidence: string;
  location_name: string | null;
  latitude: number | null;
  longitude: number | null;
  geometry: GeoJSON.Geometry | null;
  spatial_scope: SpatialScope;
  affected_latitude_min: number | null;
  affected_latitude_max: number | null;
  issued_at: string;
  starts_at: string | null;
  ends_at: string | null;
  source_metadata?: Record<string, unknown> | null;
  fingerprint: string;
  is_active: boolean;
  ingest_mode?: "live" | "fixture" | "showcase";
}

export interface AlertListResponse {
  items: Alert[];
  total: number;
  limit: number;
  offset: number;
}

export interface AlertFilters {
  source?: AlertSource;
  country?: string;
  category?: Category;
  severity?: Severity;
  active?: boolean;
  issued_after?: string;
  issued_before?: string;
  bounding_box?: string;
  limit?: number;
  offset?: number;
}

export interface ObservedEventFilters {
  source?: ObservedEventSource;
  category?: Category;
  severity?: Severity;
  active?: boolean;
  bounding_box?: string;
  limit?: number;
  offset?: number;
}
