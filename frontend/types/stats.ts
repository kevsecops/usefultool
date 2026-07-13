export interface CountryCount {
  code: string;
  count: number;
}

export interface HotspotRegion {
  region: string;
  count: number;
}

export interface Stats {
  active_count: number;
  global_risk_score: number;
  score_breakdown: Record<string, number>;
  by_country: Record<string, number>;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  top_countries: CountryCount[];
  hotspot_regions: HotspotRegion[];
  last_ingest: string | null;
}
