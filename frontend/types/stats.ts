export interface CountryCount {
  code: string;
  count: number;
}

export interface HotspotRegion {
  region: string;
  count: number;
  max_severity?: string;
  severe_or_extreme_count?: number;
}

export interface TrendAnomaly {
  dimension: string;
  key: string;
  current_count: number;
  rolling_avg: number;
  ratio: number;
}

export interface Stats {
  active_count: number;
  global_risk_score: number;
  score_breakdown: Record<string, unknown>;
  by_country: Record<string, number>;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_source: Record<string, number>;
  top_countries: CountryCount[];
  hotspot_regions: HotspotRegion[];
  trend_anomalies: TrendAnomaly[];
  last_ingest: string | null;
  canonical_event_count?: number;
  observed_event_count?: number;
}
