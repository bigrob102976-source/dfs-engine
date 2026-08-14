import { MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { buildYesterdaySummary } from "@/lib/yesterday";

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

export default function YesterdayPage() {
  const s = buildYesterdaySummary();

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
    </div>
  );
}
