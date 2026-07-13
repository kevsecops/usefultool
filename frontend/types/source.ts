export interface SourceInfo {
  id: string;
  name: string;
  healthy: boolean;
  last_fetch: string | null;
  ingest_mode?: string | null;
  alerts_fetched?: number | null;
}

export interface SourcesResponse {
  sources: SourceInfo[];
}
