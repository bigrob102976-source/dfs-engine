import type { DkSlateVegasCoverage } from "@/lib/dkVegasCoverage";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

const STATUS_LABEL: Record<string, string> = {
  LIVE_PREGAME: "LIVE PREGAME",
  PREGAME_FROZEN: "PREGAME FROZEN",
  MISSING: "MISSING",
  INVALID: "INVALID",
  IN_PLAY_ONLY: "IN-PLAY ONLY",
  NOT_MATCHED: "NOT MATCHED",
};

const STATUS_TONE: Record<string, string> = {
  LIVE_PREGAME: "bg-green/15 text-green",
  PREGAME_FROZEN: "bg-accent/15 text-accent",
  MISSING: "bg-red/15 text-red",
  INVALID: "bg-red/15 text-red",
  IN_PLAY_ONLY: "bg-yellow/15 text-yellow",
  NOT_MATCHED: "bg-text-faint/15 text-text-faint",
};

function formatLockTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** DK Slate Coverage Monitor (Milestone 25): scopes Vegas pregame
 * coverage to exactly the games on the selected real DraftKings slate
 * (lib/dkVegasCoverage.ts) -- never the raw count of MLB events
 * SportsGameOdds happens to return. */
export function DkSlateCoverageSummary({ coverage }: { coverage: DkSlateVegasCoverage }) {
  if (coverage.dkGames === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-dashed border-border bg-bg-panel p-3 text-xs text-text-faint">
        No DraftKings slate has been selected/built yet -- Vegas coverage will show here once a slate is loaded from the Optimizer.
      </div>
    );
  }

  const stats: Array<{ label: string; value: number | string; tone?: string }> = [
    { label: "DK Games", value: coverage.dkGames },
    { label: "Primary Covered", value: coverage.primaryCovered, tone: "text-green" },
    { label: "Fallback Covered", value: coverage.fallbackCovered, tone: coverage.fallbackCovered > 0 ? "text-accent" : undefined },
    { label: "Total Covered", value: coverage.pregameCovered, tone: "text-green" },
    { label: "Missing", value: coverage.missing, tone: coverage.missing > 0 ? "text-red" : undefined },
    { label: "Coverage %", value: `${coverage.coveragePercent.toFixed(0)}%`, tone: coverage.coveragePercent === 100 ? "text-green" : "text-yellow" },
  ];

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-3 shadow-[var(--shadow-card)]">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Vegas Coverage</div>
      <div className="mb-3 grid grid-cols-3 gap-3 sm:grid-cols-6">
        {stats.map((s) => (
          <div key={s.label}>
            <div className="text-[10px] uppercase tracking-wide text-text-faint">{s.label}</div>
            <div className={`text-lg font-semibold tabular-nums ${s.tone ?? "text-text"}`}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-xs">
          <thead>
            <tr className="border-b border-border-subtle text-text-faint">
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">Matchup</th>
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">DK Lock Time</th>
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">MLB Status</th>
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">Vegas Status</th>
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">Provider</th>
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">Why Missing</th>
              <th className="py-1 pr-3 text-left font-semibold uppercase tracking-wide">Last Pregame Update</th>
              <th className="py-1 pr-3 text-right font-semibold uppercase tracking-wide">Books</th>
              <th className="py-1 pr-3 text-right font-semibold uppercase tracking-wide">Total</th>
              <th className="py-1 pr-3 text-right font-semibold uppercase tracking-wide">Away Implied</th>
              <th className="py-1 text-right font-semibold uppercase tracking-wide">Home Implied</th>
            </tr>
          </thead>
          <tbody>
            {coverage.games.map((g) => (
              <tr key={g.gameInfo} className="border-b border-border-subtle/60 text-text-muted">
                <td className="py-1 pr-3 text-text">{g.matchupLabel}</td>
                <td className="py-1 pr-3">{formatLockTime(g.gameDatetimeUtc)}</td>
                <td className="py-1 pr-3">{g.mlbStatus ?? "--"}</td>
                <td className="py-1 pr-3">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_TONE[g.vegasStatus]}`}>
                    {STATUS_LABEL[g.vegasStatus]}
                  </span>
                </td>
                <td className="py-1 pr-3">
                  {g.provider ? (
                    <span className="inline-flex items-center gap-1.5">
                      {g.provider}
                      {g.fallbackUsed && (
                        <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-accent">
                          Fallback
                        </span>
                      )}
                    </span>
                  ) : (
                    "Missing"
                  )}
                </td>
                <td className="py-1 pr-3 text-text-faint">{g.missingReason ?? "--"}</td>
                <td className="py-1 pr-3">{formatLockTime(g.lastPregameUpdate)}</td>
                <td className="py-1 pr-3 text-right">{g.booksUsed.length || "--"}</td>
                <td className="py-1 pr-3 text-right">{fmt(g.consensusTotal)}</td>
                <td className="py-1 pr-3 text-right">{fmt(g.awayImplied)}</td>
                <td className="py-1 text-right">{fmt(g.homeImplied)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
