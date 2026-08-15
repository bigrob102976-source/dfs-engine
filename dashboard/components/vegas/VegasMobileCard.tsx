"use client";

import { TeamMark } from "./TeamMark";
import { VegasBadgeRow } from "./VegasBadgeRow";
import { VegasExpandedDetail } from "./VegasExpandedDetail";
import { VegasSparkline } from "./VegasSparkline";
import type { VegasSlateAnalysis } from "@/lib/gameEnvironment";
import type { VegasDisplaySettings } from "@/lib/vegasDisplaySettings";
import { buildTotalMovementSeries, deriveVegasBadges, movementTone, vegasScore, type VegasGameRow } from "@/lib/vegasIntelligence";

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}
function fmtMl(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return value > 0 ? `+${value}` : `${value}`;
}
function toneClass(tone: "positive" | "negative" | "neutral"): string {
  return tone === "positive" ? "text-green" : tone === "negative" ? "text-red" : "text-text-faint";
}
function formatGameTime(iso: string | null): string {
  if (!iso) return "Time TBD";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "Time TBD" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Mobile/narrow-viewport collapse of VegasTable's row -- desktop keeps
 * the full table (see the `lg:hidden` / `lg:block` split in
 * VegasIntelligenceBoard). Same data, same expansion content
 * (VegasExpandedDetail), just stacked into a card instead of table
 * cells. */
export function VegasMobileCard({
  row,
  analysis,
  settings,
  expanded,
  onToggleExpand,
}: {
  row: VegasGameRow;
  analysis: VegasSlateAnalysis | null;
  settings: VegasDisplaySettings;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const { game } = row;
  const vegas = game.vegas;
  const badges = deriveVegasBadges(game, analysis);
  const series = buildTotalMovementSeries(vegas);

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
      <button type="button" onClick={onToggleExpand} className="flex w-full flex-col gap-2 p-3.5 text-left" aria-expanded={expanded}>
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-text-faint">{formatGameTime(game.game_datetime_utc)}</span>
          <span className="text-text-faint">{expanded ? "▲" : "▼"}</span>
        </div>
        <div className="flex items-center gap-1.5 text-sm">
          <TeamMark team={game.away_team} />
          <span className="text-text">{game.away_team}</span>
          <span className="text-text-faint">@</span>
          <TeamMark team={game.home_team} />
          <span className="text-text">{game.home_team}</span>
        </div>
        <VegasBadgeRow badges={badges} />

        {vegas ? (
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-text-faint">Total</div>
              <div className="text-text">{fmt(vegas.current_home.total)}</div>
              <div className={`text-[11px] ${toneClass(movementTone(vegas.total_movement))}`}>
                {vegas.total_movement !== null ? `${vegas.total_movement > 0 ? "+" : ""}${vegas.total_movement.toFixed(1)}` : "--"}
              </div>
            </div>
            <div>
              <div className="text-text-faint">Moneyline</div>
              <div className="text-text">{fmtMl(vegas.current_home.moneyline)}</div>
              <div className={`text-[11px] ${toneClass(movementTone(vegas.moneyline_movement_home))}`}>
                {vegas.moneyline_movement_home !== null ? `${vegas.moneyline_movement_home > 0 ? "+" : ""}${vegas.moneyline_movement_home}` : "--"}
              </div>
            </div>
            <div>
              <div className="text-text-faint">Implied Runs</div>
              <div className="text-text">
                {game.away_team} {fmt(vegas.away_implied_runs)} / {game.home_team} {fmt(vegas.home_implied_runs)}
              </div>
            </div>
            <div>
              <div className="mb-1 text-text-faint">Line Movement</div>
              {settings.showSparklines && <VegasSparkline points={series.points} />}
            </div>
          </div>
        ) : (
          <p className="text-xs text-text-faint">Vegas lines unavailable for this game.</p>
        )}

        <div className="flex items-center gap-1.5">
          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold text-accent">ENV {game.environment_score.overall.toFixed(0)}</span>
          <span className="rounded-full bg-purple/15 px-2 py-0.5 text-[10px] font-semibold text-purple">
            VGS {vegasScore(vegas?.current_home?.total) !== null ? vegasScore(vegas?.current_home?.total)!.toFixed(0) : "--"}
          </span>
        </div>
      </button>
      {expanded && (
        <div className="border-t border-border-subtle">
          <VegasExpandedDetail row={row} analysis={analysis} />
        </div>
      )}
    </div>
  );
}
