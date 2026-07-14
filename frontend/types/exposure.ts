export type AssetType = "port" | "airport" | "power_plant";

export interface ExposureAsset {
  id: string;
  asset_type: AssetType | string;
  name: string;
  country_code?: string | null;
  region?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  importance_level: string;
  source: string;
  source_url?: string | null;
  source_asset_id?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AssetListResponse {
  items: ExposureAsset[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventAssetExposure {
  id: string;
  event_id: string;
  asset_id: string;
  exposure_type: string;
  distance_km?: number | null;
  overlap: boolean;
  confidence: string;
  rationale?: string | null;
  calculated_at: string;
  analysis_version: string;
  asset?: ExposureAsset | null;
}

export interface EventExposureListResponse {
  event_id: string;
  items: EventAssetExposure[];
  total: number;
}
