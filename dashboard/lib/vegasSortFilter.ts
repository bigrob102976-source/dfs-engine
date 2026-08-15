import { weatherRiskValue } from "./environmentSortFilter";
import { LINE_MOVEMENT_SHARP_RUNS, totalTier, vegasScore, type VegasGameRow } from "./vegasIntelligence";

export type VegasSortKey =
  | "gameTime"
  | "homeImplied"
  | "awayImplied"
  | "totalCurrent"
  | "totalMovement"
  | "moneylineMovement"
  | "environmentScore"
  | "vegasScore";

export type VegasFilterKey =
  | "all"
  | "gameTotal"
  | "highestTotals"
  | "lowestTotals"
  | "largestMoves"
  | "sharpMoney"
  | "weatherRisk"
  | "highestImplied"
  | "lowestImplied";

/** Notable moneyline movement threshold for the "Sharp Money" filter --
 * a UI-only display heuristic, distinct from LINE_MOVEMENT_SHARP_RUNS
 * (which is about the game TOTAL, not the moneyline). Chosen well inside
 * the mock provider's own +/-20 drift range (vegas.py) so the filter is
 * meaningful against today's mock data, not just a placeholder. */
const SHARP_MONEYLINE_MOVEMENT = 15;
/** "Highest/Lowest Implied Runs" filter thresholds -- a team implied
 * total notably above or below a roughly-even split of a medium (8.5)
 * game total. Display-only, never fed into scoring. */
const HIGH_IMPLIED_RUNS = 5.5;
const LOW_IMPLIED_RUNS = 3.0;

function sortValue(row: VegasGameRow, key: VegasSortKey): number | null {
  const game = row.game;
  const vegas = game.vegas;
  switch (key) {
    case "gameTime": {
      if (!game.game_datetime_utc) return null;
      const t = new Date(game.game_datetime_utc).getTime();
      return Number.isNaN(t) ? null : t;
    }
    case "homeImplied":
      return vegas?.home_implied_runs ?? null;
    case "awayImplied":
      return vegas?.away_implied_runs ?? null;
    case "totalCurrent":
      return vegas?.current_home?.total ?? null;
    case "totalMovement":
      return vegas?.total_movement ?? null;
    case "moneylineMovement":
      return vegas?.moneyline_movement_home ?? null;
    case "environmentScore":
      return game.environment_score.overall;
    case "vegasScore":
      return vegasScore(vegas?.current_home?.total);
    default:
      return null;
  }
}

/** Nulls always sort last, regardless of direction -- a missing signal
 * is never "the most" or "the least" (same rule environmentSortFilter.ts
 * uses). "totalMovement" and "moneylineMovement" sort by MAGNITUDE when
 * descending (largest move first, whichever direction) but by signed
 * value when ascending, so "Largest Moves" always means "biggest swing"
 * either way round. */
export function sortVegasRows(rows: VegasGameRow[], key: VegasSortKey, direction: "asc" | "desc" = "desc"): VegasGameRow[] {
  const magnitude = key === "totalMovement" || key === "moneylineMovement";
  const withIndex = rows.map((row, i) => ({ row, i }));
  withIndex.sort((a, b) => {
    let av = sortValue(a.row, key);
    let bv = sortValue(b.row, key);
    const aNull = av === null;
    const bNull = bv === null;
    if (aNull && bNull) return a.i - b.i;
    if (aNull) return 1;
    if (bNull) return -1;
    if (magnitude && direction === "desc") {
      av = Math.abs(av as number);
      bv = Math.abs(bv as number);
    }
    const cmp = (av as number) < (bv as number) ? -1 : (av as number) > (bv as number) ? 1 : 0;
    if (cmp === 0) return a.i - b.i;
    return direction === "asc" ? cmp : -cmp;
  });
  return withIndex.map((w) => w.row);
}

export function filterVegasRows(rows: VegasGameRow[], filter: VegasFilterKey): VegasGameRow[] {
  switch (filter) {
    case "all":
      return rows;
    case "gameTotal":
      return rows.filter((r) => r.game.vegas?.current_home?.total !== null && r.game.vegas?.current_home?.total !== undefined);
    case "highestTotals":
      return rows.filter((r) => totalTier(r.game.vegas?.current_home?.total) === "high");
    case "lowestTotals":
      return rows.filter((r) => totalTier(r.game.vegas?.current_home?.total) === "low");
    case "largestMoves":
      return rows.filter((r) => {
        const move = r.game.vegas?.total_movement;
        return move !== null && move !== undefined && Math.abs(move) >= LINE_MOVEMENT_SHARP_RUNS;
      });
    case "sharpMoney":
      return rows.filter((r) => {
        const move = r.game.vegas?.moneyline_movement_home;
        return move !== null && move !== undefined && Math.abs(move) >= SHARP_MONEYLINE_MOVEMENT;
      });
    case "weatherRisk":
      return rows.filter((r) => {
        const risk = weatherRiskValue(r.game);
        return risk !== null && risk >= 25;
      });
    case "highestImplied":
      return rows.filter((r) => {
        const vegas = r.game.vegas;
        if (!vegas) return false;
        return (vegas.home_implied_runs ?? 0) >= HIGH_IMPLIED_RUNS || (vegas.away_implied_runs ?? 0) >= HIGH_IMPLIED_RUNS;
      });
    case "lowestImplied":
      return rows.filter((r) => {
        const vegas = r.game.vegas;
        if (!vegas) return false;
        const home = vegas.home_implied_runs;
        const away = vegas.away_implied_runs;
        return (home !== null && home <= LOW_IMPLIED_RUNS) || (away !== null && away <= LOW_IMPLIED_RUNS);
      });
    default:
      return rows;
  }
}

/** Search by home/away team abbreviation or (when the pitching-matchup
 * join found one) either probable starter's name -- case-insensitive
 * substring match, same convention as PlayerTable's name filter. */
export function searchVegasRows(rows: VegasGameRow[], query: string): VegasGameRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => {
    const haystack = [r.game.home_team, r.game.away_team, r.homePitcher?.name, r.awayPitcher?.name]
      .filter((v): v is string => Boolean(v))
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}
