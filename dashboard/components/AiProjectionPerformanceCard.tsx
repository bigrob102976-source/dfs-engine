import { DataCard } from "@/components/ui/Card";
import { getSourceMetrics } from "@/lib/projectionSourceComparison";
import type { ProjectionSourceComparisonDocument, ProjectionSourceLabel } from "@/lib/projectionSourceComparison";

const SOURCE_LABELS: Record<ProjectionSourceLabel, string> = {
  independent: "Independent",
  external: "External",
  adjusted: "Adjusted",
  ai: "AI",
};

const SOURCE_ORDER: ProjectionSourceLabel[] = ["independent", "external", "adjusted", "ai"];

function fmt(v: number | null, digits = 2): string {
  return v === null ? "--" : v.toFixed(digits);
}

/** "AI Projection Performance": MAE (mean absolute error vs actual DK
 * points) by projection source, for the most recently evaluated slate.
 * Every number comes straight from the immutable
 * evaluations/<date>/projection_source_comparison_*.json artifact
 * (evaluation/projection_source_comparison.py's pure metric math over
 * evaluation/projection_source_loader.py's real snapshot reads) --
 * nothing here recomputes an error or a percentage. Pitcher-only: the
 * only actual-results source this codebase has is
 * results/<date>/pitcher_results.json. */
export function AiProjectionPerformanceCard({ doc }: { doc: ProjectionSourceComparisonDocument | null }) {
  if (!doc || doc.metrics.length === 0) {
    return (
      <DataCard title="AI Projection Performance">
        <p className="text-xs text-text-faint">No evaluated slate yet.</p>
      </DataCard>
    );
  }

  const ai = getSourceMetrics(doc, "ai");
  const independent = getSourceMetrics(doc, "independent");
  const overallMae = ai?.mae ?? independent?.mae ?? null;
  const improvement = doc.ai_vs_independent_mae_improvement_percent;
  const n = ai?.n ?? independent?.n ?? doc.actual_result_count;

  return (
    <DataCard title="AI Projection Performance">
      <div className="mb-3">
        <div className="text-[11px] uppercase tracking-wide text-text-faint">Overall MAE</div>
        <div className="text-2xl font-semibold text-purple">{fmt(overallMae)}</div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        {SOURCE_ORDER.filter((source) => doc.sources_present.includes(source)).map((source) => {
          const metrics = getSourceMetrics(doc, source);
          return (
            <div key={source} className="flex items-center justify-between rounded border border-border-subtle bg-bg-panel-raised px-2 py-1.5">
              <span className="text-text-faint">{SOURCE_LABELS[source]}</span>
              <span className={`font-semibold ${source === "ai" ? "text-purple" : "text-text"}`}>{fmt(metrics?.mae ?? null)}</span>
            </div>
          );
        })}
      </div>

      {improvement !== null && (
        <div className="mt-3 text-xs text-text-faint">
          Improvement{" "}
          <span className={`font-semibold ${improvement >= 0 ? "text-green" : "text-red"}`}>
            {improvement >= 0 ? "+" : ""}
            {improvement.toFixed(1)}%
          </span>
        </div>
      )}

      <div className="mt-2 text-[10px] text-text-faint">
        Pitchers only, n={n} · {doc.slate_date}
      </div>
    </DataCard>
  );
}
