/** Placeholder types for Phase 5-6 briefing API. */

export interface Briefing {
  id: string;
  title: string;
  summary: string;
  generated_at: string;
  type: "rule_based" | "llm";
}
