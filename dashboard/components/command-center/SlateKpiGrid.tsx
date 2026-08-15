import { AnimatedCounter } from "./AnimatedCounter";
import type { SlateKpi } from "@/lib/commandCenter";

const TONE_CLASS: Record<NonNullable<SlateKpi["tone"]>, string> = {
  positive: "text-green",
  negative: "text-red",
  neutral: "text-text",
};

function KpiValue({ kpi }: { kpi: SlateKpi }) {
  const toneClass = TONE_CLASS[kpi.tone ?? "neutral"];
  // Animate only genuinely positive numeric values -- signed movement
  // values keep their already-formatted "+/-" string as-is.
  if (kpi.numeric !== null && kpi.numeric !== undefined && kpi.numeric >= 0) {
    const decimals = typeof kpi.value === "string" && kpi.value.includes(".") ? 1 : 0;
    return (
      <span className={`text-2xl font-semibold tabular-nums ${toneClass}`}>
        <AnimatedCounter value={kpi.numeric} decimals={decimals} />
      </span>
    );
  }
  return <span className={`text-2xl font-semibold tabular-nums ${toneClass}`}>{kpi.value}</span>;
}

/** The 13 KPI cards -- "Games" through "Average Slate Score" -- every
 * value traces to lib/commandCenter.ts::buildSlateKpis, which itself
 * only reads already-built snapshots. Deliberately reuses the exact
 * responsive grid shape (`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6`)
 * the pre-existing top metric row used, so
 * app/dashboard/__tests__/responsive.test.tsx keeps passing unchanged. */
export function SlateKpiGrid({ kpis }: { kpis: SlateKpi[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi) => (
        <div
          key={kpi.key}
          className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)] transition-transform duration-150 hover:-translate-y-0.5 hover:shadow-[var(--shadow-popover)]"
        >
          <div className="text-[11px] uppercase tracking-wide text-text-faint">{kpi.label}</div>
          <div className="mt-1">
            <KpiValue kpi={kpi} />
          </div>
          {kpi.sub && <div className="mt-0.5 truncate text-[11px] text-text-faint">{kpi.sub}</div>}
        </div>
      ))}
    </div>
  );
}
