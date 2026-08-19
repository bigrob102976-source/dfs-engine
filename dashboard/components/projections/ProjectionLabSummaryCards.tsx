import type { ProjectionLabSummary } from "@/lib/projectionLab";

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 shadow-[var(--shadow-card)]">
      <div className="text-[10px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-text">{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11px] text-text-faint">{sub}</div>}
    </div>
  );
}

/** PROJECTION LAB summary strip (Milestone 27) -- every card is a
 * trivial aggregate of lib/projectionLab.ts's already-computed rows,
 * never a new calculation. */
export function ProjectionLabSummaryCards({ summary }: { summary: ProjectionLabSummary }) {
  const pct = (n: number) => (summary.players > 0 ? `${Math.round((n / summary.players) * 100)}%` : "--");
  // Milestone 30.1: Native/AI coverage is measured primarily against
  // eligible (confirmed starter) players -- hundreds of relief pitchers/
  // bench hitters must never make coverage look artificially poor.
  const eligiblePct = (n: number) => (summary.eligiblePlayers > 0 ? `${Math.round((n / summary.eligiblePlayers) * 100)}%` : "--");

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
      <Card label="Raw DK Players" value={String(summary.players)} />
      <Card label="Optimizer Eligible" value={String(summary.eligiblePlayers)} />
      <Card label="BlueCollar Coverage" value={`${summary.blueCollarCoverage} (${pct(summary.blueCollarCoverage)})`} />
      <Card
        label="Native Eligible Coverage"
        value={`${summary.nativeEligibleCoverage}/${summary.eligiblePlayers} (${eligiblePct(summary.nativeEligibleCoverage)})`}
        sub={`${summary.nativeCoverage} of all preserved DK rows`}
      />
      <Card
        label="AI Eligible Coverage"
        value={`${summary.aiEligibleCoverage}/${summary.eligiblePlayers} (${eligiblePct(summary.aiEligibleCoverage)})`}
        sub={`${summary.aiCoverage} of all preserved DK rows`}
      />
      <Card label="Avg Native Projection" value={summary.averageNativeProjection === null ? "--" : summary.averageNativeProjection.toFixed(1)} />
      <Card label="Avg AI Adjustment" value={summary.averageAiAdjustment === null ? "--" : `${summary.averageAiAdjustment >= 0 ? "+" : ""}${summary.averageAiAdjustment.toFixed(1)}`} />
      <Card
        label="Largest AI Upgrade"
        value={summary.largestAiUpgrade ? `+${summary.largestAiUpgrade.aiVsNativeDelta!.toFixed(1)}` : "--"}
        sub={summary.largestAiUpgrade?.name}
      />
      <Card
        label="Largest AI Downgrade"
        value={summary.largestAiDowngrade ? summary.largestAiDowngrade.aiVsNativeDelta!.toFixed(1) : "--"}
        sub={summary.largestAiDowngrade?.name}
      />
      <Card
        label="Largest BM vs BlueCollar Diff"
        value={summary.largestBigMoneyVsBlueCollarDifference ? `${summary.largestBigMoneyVsBlueCollarDifference.bigMoneyVsBlueCollarDelta! >= 0 ? "+" : ""}${summary.largestBigMoneyVsBlueCollarDifference.bigMoneyVsBlueCollarDelta!.toFixed(1)}` : "--"}
        sub={summary.largestBigMoneyVsBlueCollarDifference?.name}
      />
    </div>
  );
}
