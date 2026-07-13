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

export interface BriefingContent {
  generated_at: string;
  type: "rule_based" | "llm";
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
