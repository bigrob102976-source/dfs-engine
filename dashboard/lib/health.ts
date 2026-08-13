import type { ArtifactState } from "./types";

export type HealthColor = "green" | "yellow" | "red" | "gray";

/** Simple traffic-light thresholds for a completeness ratio (count/total). */
export function ratioHealth(count: number, total: number): HealthColor {
  if (total <= 0) return "gray";
  const ratio = count / total;
  if (ratio >= 0.95) return "green";
  if (ratio >= 0.5) return "yellow";
  return "red";
}

export interface CompletenessRow {
  label: string;
  count: number;
  total: number;
  color: HealthColor;
}

/** Builds Model Health rows directly from a Research Quality Report
 * already computed by the Python pipeline (research/quality_report.py's
 * `{ total_pitchers | total_hitters, counts: {label: count} }` embedded
 * in the pitcher/batter snapshot) -- the dashboard never recomputes
 * completeness itself, only renders it, so it can never drift from the
 * source of truth. */
export function qualityReportToRows(
  qualityReport: { counts?: Record<string, number> } | null | undefined,
  total: number,
): CompletenessRow[] {
  if (!qualityReport?.counts) return [];
  return Object.entries(qualityReport.counts).map(([label, count]) => ({
    label,
    count,
    total,
    color: ratioHealth(count, total),
  }));
}

/** Determines whether a pipeline stage is ready/missing/outdated. A
 * stage is "outdated" when it exists but was generated BEFORE the
 * upstream artifact it depends on -- a real staleness signal (e.g. the
 * DK pool was rebuilt after ownership was last projected). */
export function pipelineStageStatus(params: {
  exists: boolean;
  generatedAtUtc?: string | null;
  upstreamGeneratedAtUtc?: string | null;
}): ArtifactState {
  if (!params.exists) return "missing";
  if (params.upstreamGeneratedAtUtc && params.generatedAtUtc) {
    const own = Date.parse(params.generatedAtUtc);
    const upstream = Date.parse(params.upstreamGeneratedAtUtc);
    if (!Number.isNaN(own) && !Number.isNaN(upstream) && own < upstream) {
      return "outdated";
    }
  }
  return "ready";
}
