import type { GameEnvironmentReport } from "./gameEnvironment";

export type EnvironmentSortKey = "score" | "total" | "weatherRisk" | "bullpenRisk" | "stack";
export type ParkFilter = "all" | "pitcher" | "hitter";

/** Mirrors the "Hitter friendly park." / "Pitcher friendly park." thresholds
 * research/game_environment/summary.py applies to the same park_factor
 * field, so a game classified "Hitter Park" here always agrees with its
 * own AI Summary bullet. */
const HITTER_PARK_FACTOR_THRESHOLD = 108;
const PITCHER_PARK_FACTOR_THRESHOLD = 92;

export function parkTier(game: GameEnvironmentReport): "hitter" | "pitcher" | "neutral" | null {
  const factor = game.ballpark?.park_factor;
  if (factor === null || factor === undefined) return null;
  if (factor >= HITTER_PARK_FACTOR_THRESHOLD) return "hitter";
  if (factor <= PITCHER_PARK_FACTOR_THRESHOLD) return "pitcher";
  return "neutral";
}

/** Average of whichever bullpen strength scores exist for the game (home,
 * away, or both) -- null only when neither side has a score. Lower means
 * weaker/riskier bullpens, matching bullpen.py's strength_score scale. */
export function averageBullpenStrength(game: GameEnvironmentReport): number | null {
  const scores = [game.bullpen_home?.strength_score, game.bullpen_away?.strength_score].filter(
    (v): v is number => v !== null && v !== undefined,
  );
  if (scores.length === 0) return null;
  return scores.reduce((sum, v) => sum + v, 0) / scores.length;
}

/** Higher means riskier weather (whichever of delay/postponement risk is
 * larger) -- null when no weather snapshot exists for the game. */
export function weatherRiskValue(game: GameEnvironmentReport): number | null {
  if (!game.weather) return null;
  const delay = game.weather.delay_risk_percent ?? 0;
  const postponement = game.weather.postponement_risk_percent ?? 0;
  return Math.max(delay, postponement);
}

function sortValue(game: GameEnvironmentReport, key: EnvironmentSortKey): number | null {
  switch (key) {
    case "score":
      return game.environment_score.overall;
    case "total":
      return game.vegas?.current_home?.total ?? null;
    case "weatherRisk":
      return weatherRiskValue(game);
    case "bullpenRisk":
      return averageBullpenStrength(game);
    case "stack":
      return game.environment_score.stack;
    default:
      return null;
  }
}

/** "bullpenRisk" is the one sort where risk rises as the value falls (a
 * weak bullpen has a LOW strength score), so it sorts ascending by
 * default while every other key sorts descending ("highest first" reads
 * naturally for score/total/weather-risk/stack). Nulls always sort last,
 * regardless of direction -- a missing signal is never "the most". */
export function sortGames(games: GameEnvironmentReport[], key: EnvironmentSortKey): GameEnvironmentReport[] {
  const ascending = key === "bullpenRisk";
  const withIndex = games.map((game, i) => ({ game, i }));
  withIndex.sort((a, b) => {
    const av = sortValue(a.game, key);
    const bv = sortValue(b.game, key);
    const aNull = av === null;
    const bNull = bv === null;
    if (aNull && bNull) return a.i - b.i;
    if (aNull) return 1;
    if (bNull) return -1;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    if (cmp === 0) return a.i - b.i;
    return ascending ? cmp : -cmp;
  });
  return withIndex.map((w) => w.game);
}

export function filterGamesByPark(games: GameEnvironmentReport[], filter: ParkFilter): GameEnvironmentReport[] {
  if (filter === "all") return games;
  return games.filter((g) => parkTier(g) === filter);
}
