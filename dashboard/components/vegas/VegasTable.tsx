"use client";

import { Fragment } from "react";

import { TeamMark } from "./TeamMark";
import { VegasBadgeRow } from "./VegasBadgeRow";
import { VegasExpandedDetail } from "./VegasExpandedDetail";
import { VegasSparkline } from "./VegasSparkline";
import type { VegasDisplaySettings } from "@/lib/vegasDisplaySettings";
import type { VegasSlateAnalysis } from "@/lib/gameEnvironment";
import { buildTotalMovementSeries, deriveVegasBadges, movementPercent, movementTone, vegasScore, type VegasGameRow } from "@/lib/vegasIntelligence";
import type { VegasSortKey } from "@/lib/vegasSortFilter";

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}
function fmtMl(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return value > 0 ? `+${value}` : `${value}`;
}
function fmtPercent(value: number | null): string {
  if (value === null) return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}
function fmtDiff(value: number | null, digits = 1): string {
  if (value === null) return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}
function toneClass(tone: "positive" | "negative" | "neutral"): string {
  return tone === "positive" ? "text-green" : tone === "negative" ? "text-red" : "text-text-faint";
}
function formatGameTime(iso: string | null): string {
  if (!iso) return "Time TBD";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "Time TBD" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

const COLUMN_HEADERS: Array<{ key: VegasSortKey | null; label: string }> = [
  { key: "gameTime", label: "Game Time" },
  { key: null, label: "Matchup" },
  { key: "homeImplied", label: "Team Implied Runs" },
  { key: "totalCurrent", label: "Game Total" },
  { key: "moneylineMovement", label: "Moneyline" },
  { key: "totalMovement", label: "Line Movement" },
  { key: "environmentScore", label: "AI" },
];

export function VegasTable({
  rows,
  analysis,
  settings,
  sortKey,
  sortDir,
  onSort,
  expandedId,
  onToggleExpand,
}: {
  rows: VegasGameRow[];
  analysis: VegasSlateAnalysis | null;
  settings: VegasDisplaySettings;
  sortKey: VegasSortKey;
  sortDir: "asc" | "desc";
  onSort: (key: VegasSortKey) => void;
  expandedId: string | null;
  onToggleExpand: (gameId: string) => void;
}) {
  const cellPad = settings.compactMode ? "px-3 py-1.5" : "px-3 py-2.5";

  return (
    <div className="hidden overflow-x-auto rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)] lg:block">
      <table className="w-full min-w-[1100px] text-xs">
        <thead>
          <tr className="border-b border-border bg-bg-panel-raised text-text-faint">
            {COLUMN_HEADERS.map((col) => (
              <th
                key={col.label}
                onClick={col.key ? () => onSort(col.key!) : undefined}
                className={`${cellPad} text-left font-semibold uppercase tracking-wide ${col.key ? "cursor-pointer select-none hover:text-text" : ""}`}
              >
                {col.label}
                {col.key === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
              </th>
            ))}
            <th className={cellPad} aria-label="Expand" />
          </tr>
        </thead>
        <tbody>
          {rows.map(({ game, homePitcher, awayPitcher }) => {
            const vegas = game.vegas;
            const badges = deriveVegasBadges(game, analysis);
            const expanded = expandedId === game.game_id;
            const series = buildTotalMovementSeries(vegas);
            const totalMovePct = vegas ? movementPercent(vegas.opening_home.total, vegas.current_home.total) : null;
            const mlMovePct = vegas ? movementPercent(vegas.opening_home.moneyline, vegas.current_home.moneyline) : null;

            return (
              <Fragment key={game.game_id}>
                <tr
                  onClick={() => onToggleExpand(game.game_id)}
                  className="cursor-pointer border-b border-border-subtle transition-colors duration-150 hover:bg-bg-panel-raised"
                  aria-expanded={expanded}
                >
                  <td className={`${cellPad} text-text-muted`}>{formatGameTime(game.game_datetime_utc)}</td>

                  <td className={cellPad}>
                    <div className="flex items-center gap-1.5">
                      <TeamMark team={game.away_team} />
                      <span className="text-text">{game.away_team}</span>
                      <span className="text-text-faint">@</span>
                      <TeamMark team={game.home_team} />
                      <span className="text-text">{game.home_team}</span>
                    </div>
                    <div className="mt-1">
                      <VegasBadgeRow badges={badges} />
                    </div>
                  </td>

                  <td className={cellPad}>
                    {vegas ? (
                      <div className="flex flex-col gap-0.5">
                        <span className="text-text-muted">
                          {game.away_team} {fmt(vegas.away_implied_runs)}
                        </span>
                        <span className="text-text-muted">
                          {game.home_team} {fmt(vegas.home_implied_runs)}
                        </span>
                      </div>
                    ) : (
                      <span className="text-text-faint">--</span>
                    )}
                  </td>

                  <td className={cellPad}>
                    {vegas ? (
                      <div className="flex flex-col gap-0.5">
                        <span className="text-text">
                          {settings.showOpeningLines && (
                            <>
                              <span className="text-text-faint">{fmt(vegas.opening_home.total)} → </span>
                            </>
                          )}
                          {fmt(vegas.current_home.total)}
                        </span>
                        <span className={`${toneClass(movementTone(vegas.total_movement))} text-[11px]`}>
                          {fmtDiff(vegas.total_movement)}
                          {settings.showMovementPercent && vegas.total_movement !== null ? ` (${fmtPercent(totalMovePct)})` : ""}
                        </span>
                      </div>
                    ) : (
                      <span className="text-text-faint">--</span>
                    )}
                  </td>

                  <td className={cellPad}>
                    {vegas ? (
                      <div className="flex flex-col gap-0.5">
                        <span className="text-text">
                          {settings.showOpeningLines && <span className="text-text-faint">{fmtMl(vegas.opening_home.moneyline)} → </span>}
                          {fmtMl(vegas.current_home.moneyline)}
                        </span>
                        <span className={`${toneClass(movementTone(vegas.moneyline_movement_home))} text-[11px]`}>
                          {fmtDiff(vegas.moneyline_movement_home, 0)}
                          {settings.showMovementPercent && vegas.moneyline_movement_home !== null ? ` (${fmtPercent(mlMovePct)})` : ""}
                        </span>
                      </div>
                    ) : (
                      <span className="text-text-faint">--</span>
                    )}
                  </td>

                  <td className={cellPad}>
                    <div className="flex items-center gap-2">
                      {settings.showSparklines && <VegasSparkline points={series.points} />}
                      {!settings.compactMode && (
                        <div className="flex flex-col gap-0.5 text-[10px] text-text-faint">
                          <span>O {fmt(series.open)} · C {fmt(series.current)}</span>
                          <span>H {fmt(series.highest)} · L {fmt(series.lowest)}</span>
                        </div>
                      )}
                    </div>
                  </td>

                  <td className={cellPad}>
                    <div className="flex items-center gap-1.5">
                      <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold text-accent">
                        ENV {game.environment_score.overall.toFixed(0)}
                      </span>
                      <span className="rounded-full bg-purple/15 px-2 py-0.5 text-[10px] font-semibold text-purple">
                        VGS {vegasScore(vegas?.current_home?.total) !== null ? vegasScore(vegas?.current_home?.total)!.toFixed(0) : "--"}
                      </span>
                    </div>
                    {game.summary.bullet_points[0] && (
                      <div className="mt-1 max-w-[160px] truncate text-[10px] italic text-purple" title={game.summary.bullet_points[0]}>
                        ✦ {game.summary.bullet_points[0]}
                      </div>
                    )}
                  </td>

                  <td className={`${cellPad} text-right text-text-faint`}>{expanded ? "▲" : "▼"}</td>
                </tr>
                {expanded && (
                  <tr className="border-b border-border-subtle bg-bg-panel-raised/40">
                    <td colSpan={COLUMN_HEADERS.length + 1} className="p-0">
                      <VegasExpandedDetail row={{ game, homePitcher, awayPitcher }} analysis={analysis} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={COLUMN_HEADERS.length + 1} className="px-3 py-8 text-center text-text-faint">
                No games match the current filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
