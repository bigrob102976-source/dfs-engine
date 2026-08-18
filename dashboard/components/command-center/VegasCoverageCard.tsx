import Link from "next/link";

import type { DkSlateVegasCoverage } from "@/lib/dkVegasCoverage";

/** Compact "Vegas Coverage" card for the selected DK slate (Milestone
 * 25) -- clicking opens /dashboard/vegas, which defaults to the same
 * PREGAME DFS view this card summarizes. A distinct card (not folded
 * into SlateKpiGrid) because it's the one KPI that should be clickable
 * straight through to its own detail page. */
export function VegasCoverageCard({ coverage }: { coverage: DkSlateVegasCoverage }) {
  const allCovered = coverage.dkGames > 0 && coverage.pregameCovered === coverage.dkGames;
  const toneClass = coverage.dkGames === 0 ? "text-text-faint" : allCovered ? "text-green" : coverage.pregameCovered === 0 ? "text-red" : "text-yellow";

  return (
    <Link
      href="/dashboard/vegas"
      className="block rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)] transition-transform duration-150 hover:-translate-y-0.5 hover:shadow-[var(--shadow-popover)]"
    >
      <div className="text-[11px] uppercase tracking-wide text-text-faint">Vegas Coverage</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>
        {coverage.dkGames === 0 ? "--" : `${coverage.pregameCovered} / ${coverage.dkGames}`}
      </div>
      <div className={`mt-0.5 text-[11px] ${toneClass}`}>
        {coverage.dkGames === 0
          ? "No DK slate selected"
          : allCovered
            ? "ALL DK GAMES COVERED"
            : `${coverage.coveragePercent.toFixed(0)}%`}
      </div>
      {coverage.dkGames > 0 && (
        <div className="mt-2 flex gap-3 text-[10px] text-text-faint">
          <span>
            Primary: <span className="text-text-muted">{coverage.primaryCovered}</span>
          </span>
          <span>
            Fallback: <span className={coverage.fallbackCovered > 0 ? "text-accent" : "text-text-muted"}>{coverage.fallbackCovered}</span>
          </span>
          <span>
            Missing: <span className={coverage.missing > 0 ? "text-red" : "text-text-muted"}>{coverage.missing}</span>
          </span>
        </div>
      )}
    </Link>
  );
}
