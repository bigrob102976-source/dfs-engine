import { MetricCard } from "@/components/ui/Card";
import { PageHeader, SectionHeader } from "@/components/ui/Header";
import { ImportContestResultsCard } from "@/components/results/ImportContestResultsCard";
import { loadLatestProjectionSourceComparison } from "@/lib/projectionSourceComparison";
import { buildYesterdaySummary } from "@/lib/yesterday";

function fmt(v: number | null, digits = 2): string {
  return v === null ? "n/a" : v.toFixed(digits);
}

// Milestone 27: canonical source labels -- never a bare source key.
const SOURCE_LABEL: Record<string, string> = {
  independent: "Legacy",
  external: "BlueCollar",
  adjusted: "BlueCollar (Adjusted)",
  native: "Big Money Native",
  ai: "Big Money AI",
};

export const dynamic = "force-dynamic";

function TrendArrow({ delta, lowerIsBetter = true }: { delta: number | null; lowerIsBetter?: boolean }) {
  if (delta === null || delta === 0) return null;
  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return (
    <span className={improved ? "text-green" : "text-red"}>
      {improved ? "▼" : "▲"} {Math.abs(delta).toFixed(2)}
    </span>
  );
}

function MissCard({ title, record }: { title: string; record: Record<string, unknown> | null }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <div className="mb-2 text-[11px] uppercase tracking-wide text-text-faint">{title}</div>
      {record ? (
        <div className="text-sm text-text">
          {String(record.name ?? "unknown")}
          <div className="mt-1 text-xs text-text-muted">
            {Object.entries(record)
              .filter(([k]) => k !== "name")
              .slice(0, 4)
              .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : v}`)
              .join(" · ")}
          </div>
        </div>
      ) : (
        <div className="text-xs text-text-faint">No data available.</div>
      )}
    </div>
  );
}

export default async function YesterdayPage() {
  const s = await buildYesterdaySummary();
  const projectionComparison = s.date ? await loadLatestProjectionSourceComparison(s.date) : null;

  if (!s.date) {
    return (
      <div>
        <PageHeader title="Results" />
        <div className="mt-4 rounded-[var(--radius-card)] border border-dashed border-border bg-bg-panel p-8 text-center text-sm text-text-faint shadow-[var(--shadow-card)]">
          <div className="mb-2 text-2xl" aria-hidden="true">
            📉
          </div>
          Historical data unavailable for this slate.
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Results" description={`Most recently evaluated slate: ${s.date}`} />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Pitcher MAE" value={s.pitcherMae?.toFixed(2) ?? "n/a"} trend={<TrendArrow delta={s.trend?.pitcherMaeDelta ?? null} />} />
        <MetricCard label="Ownership MAE" value={s.ownershipMae?.toFixed(2) ?? "n/a"} trend={<TrendArrow delta={s.trend?.ownershipMaeDelta ?? null} />} />
        <MetricCard label="Projection Correlation" value={s.projectionCorrelation?.toFixed(3) ?? "n/a"} />
        <MetricCard label="Ownership Correlation" value={s.ownershipCorrelation?.toFixed(3) ?? "n/a"} />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <MissCard title="Top Projection Miss" record={s.topProjectionMiss} />
        <MissCard title="Worst Ownership Miss" record={s.worstOwnershipMiss} />
        <MissCard title="Best Leverage Call" record={s.bestLeverageCall} />
        <MissCard title="Worst Chalk Miss" record={s.worstChalkMiss} />
      </div>

      <div className="mt-4">
        <ImportContestResultsCard date={s.date} slateId={null} />
      </div>

      {projectionComparison && projectionComparison.metrics.length > 0 && (
        <div className="mt-6">
          <SectionHeader title="Projection Source Performance" />
          <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
            <table className="w-full min-w-[560px] text-xs">
              <thead>
                <tr className="text-left text-text-faint">
                  <th className="pb-2 font-medium">Source</th>
                  <th className="pb-2 text-right font-medium">N</th>
                  <th className="pb-2 text-right font-medium">MAE</th>
                  <th className="pb-2 text-right font-medium">RMSE</th>
                  <th className="pb-2 text-right font-medium">Corr</th>
                  <th className="pb-2 text-right font-medium">Rank Corr</th>
                  <th className="pb-2 text-right font-medium">Top 5</th>
                  <th className="pb-2 text-right font-medium">Top 10</th>
                </tr>
              </thead>
              <tbody>
                {projectionComparison.metrics.map((m) => (
                  <tr key={m.source} className="border-t border-border-subtle">
                    <td className={`py-1.5 ${m.source === "ai" ? "font-semibold text-purple" : "text-text"}`}>{SOURCE_LABEL[m.source] ?? m.source}</td>
                    <td className="py-1.5 text-right text-text-muted">{m.n}</td>
                    <td className={`py-1.5 text-right font-semibold ${m.source === "ai" ? "text-purple" : "text-text"}`}>{fmt(m.mae)}</td>
                    <td className="py-1.5 text-right text-text-muted">{fmt(m.rmse)}</td>
                    <td className="py-1.5 text-right text-text-muted">{fmt(m.correlation, 3)}</td>
                    <td className="py-1.5 text-right text-text-muted">{fmt(m.rank_correlation, 3)}</td>
                    <td className="py-1.5 text-right text-text-muted">{m.top5_hit_rate !== null ? `${Math.round(m.top5_hit_rate * 100)}%` : "n/a"}</td>
                    <td className="py-1.5 text-right text-text-muted">{m.top10_hit_rate !== null ? `${Math.round(m.top10_hit_rate * 100)}%` : "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {projectionComparison.ai_vs_independent_mae_improvement_percent !== null && (
            <p className="mt-2 text-xs text-text-faint">
              AI vs Independent MAE improvement:{" "}
              <span className={`font-semibold ${projectionComparison.ai_vs_independent_mae_improvement_percent >= 0 ? "text-green" : "text-red"}`}>
                {projectionComparison.ai_vs_independent_mae_improvement_percent >= 0 ? "+" : ""}
                {projectionComparison.ai_vs_independent_mae_improvement_percent.toFixed(1)}%
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
