export interface AffectedRegion {
  region: string;
  alert_count: number;
  max_severity: string;
  alert_ids: string[];
}

export interface SourceCount {
  source: string;
  label: string;
  count: number;
}

export interface CountryCount {
  code: string;
  count: number;
}

export interface MajorEvent {
  title: string;
  severity: string;
  source: string;
  category?: string;
  region?: string;
  alert_id: string;
}

export interface CrossBorderPattern {
  type: string;
  description: string;
  alert_ids: string[];
  confidence: string;
}

export interface TrendAnomaly {
  dimension: string;
  key: string;
  current_count: number;
  rolling_avg: number;
  ratio: number;
}

export interface PotentialImplications {
  economy: string[];
  logistics: string[];
  infrastructure: string[];
  technology: string[];
  finance: string[];
}

export interface ObservedEventItem {
  canonical_event_id: string;
  event_title: string;
  event_type?: string;
  severity: string;
  observed_count: number;
  sources: string[];
  source_ids: string[];
}

export interface ObservedEventsSection {
  summary: string;
  items: ObservedEventItem[];
  confidence: string;
}

export interface VerifiedExposureItem {
  event_id: string;
  event_title: string;
  asset_name: string;
  asset_type: string;
  exposure_type: string;
  confidence: string;
  source_ids: string[];
}

export interface VerifiedExposureSection {
  summary: string;
  items: VerifiedExposureItem[];
  confidence: string;
}

export interface SourcedClaim {
  description: string;
  confidence: string;
  evidence_level?: string;
  source_ids: string[];
}

export interface SectionConfidence {
  observed_events: string;
  verified_exposure: string;
  potential_implications: string;
  confirmed_impacts: string;
  cross_border_relevance: string;
  technology_infrastructure_risks: string;
}

export interface BriefingContent {
  generated_at: string;
  type: "rule_based" | "llm";
  active_count: number;
  overall_risk_score: number;
  summary: string;
  overall_confidence: "low" | "medium" | "high";
  by_source: SourceCount[];
  top_countries: CountryCount[];
  affected_regions: AffectedRegion[];
  major_events: MajorEvent[];
  cross_border_patterns: CrossBorderPattern[];
  trend_anomalies: TrendAnomaly[];
  potential_implications: PotentialImplications;
  observed_events?: ObservedEventsSection;
  verified_exposure?: VerifiedExposureSection;
  confirmed_impacts?: SourcedClaim[];
  cross_border_relevance?: SourcedClaim[];
  technology_infrastructure_risks?: SourcedClaim[];
  evidence_gaps?: string[];
  section_confidence?: SectionConfidence;
  limitations: string[];
  source_alert_ids: string[];
  score_breakdown: Record<string, unknown>;
}

export interface Briefing {
  id: string;
  generated_at: string;
  type: "rule_based" | "llm";
  overall_risk_score: number;
  overall_confidence: "low" | "medium" | "high";
  content: BriefingContent;
  source_alert_ids: string[];
  llm_model: string | null;
}

export interface BriefingListResponse {
  items: Briefing[];
  total: number;
  limit: number;
  offset: number;
}
