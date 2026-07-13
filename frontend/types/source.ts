export interface SourceInfo {
  id: string;
  name: string;
  healthy: boolean;
  last_fetch: string | null;
}

export interface SourcesResponse {
  sources: SourceInfo[];
}
