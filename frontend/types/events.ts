import type { Category, Severity } from "@/types/alert";

export type Confidence = "low" | "medium" | "high";

export type MemberType = "alert" | "observed_event";
export type LinkConfidence = "high" | "medium" | "low";

export interface CanonicalEventMember {
  member_type: MemberType;
  member_id: string;
  link_confidence: LinkConfidence;
  link_reason?: string | null;
  source?: string | null;
  title?: string | null;
}

export interface CanonicalEvent {
  id: string;
  event_type?: string | null;
  title: string;
  status: string;
  severity: Severity;
  geometry?: GeoJSON.Geometry | null;
  spatial_scope: string;
  started_at: string;
  updated_at: string;
  ended_at?: string | null;
  confidence: Confidence;
  primary_source_id?: string | null;
  correlation_reason?: string | null;
  correlation_version: string;
  is_active: boolean;
  member_count: number;
  members: CanonicalEventMember[];
}

export interface CanonicalEventListResponse {
  items: CanonicalEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface ObservedEvent {
  id: string;
  source: string;
  source_event_id: string;
  source_url?: string | null;
  title: string;
  description?: string | null;
  event_type?: string | null;
  category: Category;
  severity: Severity;
  status: string;
  confidence: Confidence;
  country_code?: string | null;
  region?: string | null;
  location_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  geometry?: GeoJSON.Geometry | null;
  spatial_scope: string;
  issued_at: string;
  starts_at?: string | null;
  ends_at?: string | null;
  updated_at_source?: string | null;
  ingested_at: string;
  fingerprint: string;
  is_active: boolean;
  ingest_mode?: string;
}

export interface ObservedEventListResponse {
  items: ObservedEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventSourcesResponse {
  canonical_event_id: string;
  alerts: Array<{
    id: string;
    source: string;
    source_alert_id: string;
    title: string;
    category: string;
    severity: string;
    issued_at: string;
    is_active: boolean;
  }>;
  observed_events: Array<{
    id: string;
    source: string;
    source_event_id: string;
    title: string;
    category: string;
    severity: string;
    issued_at: string;
    is_active: boolean;
  }>;
}

export interface ImplicationCandidate {
  id: string;
  canonical_event_id: string;
  category: string;
  title: string;
  description?: string | null;
  affected_region?: string | null;
  related_asset_ids: string[];
  supporting_source_ids: string[];
  confidence: Confidence;
  evidence_level: string;
  rationale?: string | null;
  missing_data?: string | null;
  generated_by: string;
  created_at: string;
}

export interface EventImplicationsResponse {
  event_id: string;
  items: ImplicationCandidate[];
  total: number;
}

export interface SpaceWeatherResponse extends ObservedEventListResponse {}

export interface FireClustersResponse extends ObservedEventListResponse {}
