import type { GameEnvironmentReport, SlateEnvironmentReport, VegasSlateAnalysis, VegasSnapshot } from "./gameEnvironment";
import type { PitcherRecord } from "./types";

// Milestone DS3 -- Vegas Intelligence Board. This module is a pure,
// read-only derivation layer over the immutable Game Environment
// snapshot (research/game_environment/, Milestone DS2) -- it never
// recomputes or overrides anything in Environment Score, Projections,
// Ownership, or the Optimizer. Every threshold below mirrors
// config/game_environment_config.py exactly so a game classified
// "High Total" or "Sharp Move" here can never disagree with the
// Python engine's own vegas.py / scoring.py / summary.py.

export const TOTAL_HIGH_THRESHOLD = 9.5;
export const TOTAL_LOW_THRESHOLD = 7.5;
export const LINE_MOVEMENT_SHARP_RUNS = 1.0;
/** A materially larger/faster move than "sharp" -- not a Python engine
 * concept (research/game_environment/vegas.py only defines "sharp"),
 * so this threshold lives here only, clearly documented, and is
 * strictly stricter than LINE_MOVEMENT_SHARP_RUNS (every "steam" game
 * is also a "sharp" game). */
export const LINE_MOVEMENT_STEAM_RUNS = 1.5;

export type TotalTier = "high" | "low" | "medium";

/** Mirrors research/game_environment/vegas.py::total_tier() exactly. */
export function totalTier(total: number | null | undefined): TotalTier {
  if (total === null || total === undefined) return "medium";
  if (total >= TOTAL_HIGH_THRESHOLD) return "high";
  if (total <= TOTAL_LOW_THRESHOLD) return "low";
  return "medium";
}

/** Mirrors research/game_environment/scoring.py::_vegas_component()
 * exactly (total 7.5 -> 0, total 9.5+ -> 100) -- a pure, display-only
 * recomputation for the "Vegas Score" column. Never fed back into
 * Environment Score or any projection. */
export function vegasScore(total: number | null | undefined): number | null {
  if (total === null || total === undefined) return null;
  const clamped = Math.min(Math.max(total, TOTAL_LOW_THRESHOLD), TOTAL_HIGH_THRESHOLD);
  return ((clamped - TOTAL_LOW_THRESHOLD) / (TOTAL_HIGH_THRESHOLD - TOTAL_LOW_THRESHOLD)) * 100;
}

/** Milestone 24: the snapshot only stores CURRENT team implied runs
 * (home_implied_runs/away_implied_runs) -- there is no separate "first
 * observed implied runs" field. Rather than invent a NEW formula for
 * it, this applies the exact SAME real, documented methodology
 * research/game_environment/providers/implied_runs.py uses for current
 * implied runs -- splitting the total by the run line's own margin --
 * against the FIRST-OBSERVED total/run line instead (opening_home).
 * Never labeled a real sportsbook "opening" (see providers/normalizer.py's
 * module docstring); this project's own first-observed-today value. */
export function firstObservedImpliedRuns(vegas: VegasSnapshot): { home: number | null; away: number | null } {
  const total = vegas.opening_home.total;
  const homeRunLine = vegas.opening_home.run_line;
  if (total === null || homeRunLine === null) return { home: null, away: null };
  const marginHome = -homeRunLine;
  const home = Math.round((total / 2 + marginHome / 2) * 100) / 100;
  const away = Math.round((total / 2 - marginHome / 2) * 100) / 100;
  if (home < 0 || away < 0) return { home: null, away: null };
  return { home, away };
}

export function movementPercent(opening: number | null, current: number | null): number | null {
  if (opening === null || current === null || opening === 0) return null;
  return ((current - opening) / Math.abs(opening)) * 100;
}

export type MovementTone = "positive" | "negative" | "neutral";

/** Green = positive movement, red = negative, blue/neutral = flat --
 * the milestone's own literal color law for movement, a DIFFERENT axis
 * than EnvironmentScoreBadge's hitting/pitching color law (which reads
 * "high total = red"). Movement direction always reads intuitively:
 * up = green, down = red. */
export function movementTone(delta: number | null): MovementTone {
  if (delta === null || Math.abs(delta) < 1e-9) return "neutral";
  return delta > 0 ? "positive" : "negative";
}

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

export type VegasBadgeKey = "highestTotal" | "sharpMove" | "steamMove" | "trapGame" | "pitchersDuel" | "homeFavorite" | "roadFavorite";

export interface VegasBadge {
  key: VegasBadgeKey;
  label: string;
  tone: "positive" | "negative" | "neutral" | "interactive";
}

const BADGE_LABELS: Record<VegasBadgeKey, string> = {
  highestTotal: "Highest Total",
  sharpMove: "Sharp Move",
  steamMove: "Steam Move",
  trapGame: "Trap Game",
  pitchersDuel: "Pitcher's Duel",
  homeFavorite: "Home Favorite",
  roadFavorite: "Road Favorite",
};

/** Deterministic badge derivation -- every badge is a pure function of
 * already-computed, real fields (never a guess). "Trap Game" is the one
 * genuinely heuristic badge: the slate's biggest favorite whose total is
 * simultaneously moving DOWN, i.e. the line is quietly fading the
 * popular/chalk side of the game -- worth a second look, not a
 * prediction of outcome. */
export function deriveVegasBadges(game: GameEnvironmentReport, analysis: VegasSlateAnalysis | null): VegasBadge[] {
  const vegas = game.vegas;
  if (!vegas) return [];
  const badges: VegasBadge[] = [];

  if (analysis?.highest_total_game_id === game.game_id) badges.push({ key: "highestTotal", label: BADGE_LABELS.highestTotal, tone: "negative" });

  const absMove = vegas.total_movement !== null ? Math.abs(vegas.total_movement) : 0;
  if (absMove >= LINE_MOVEMENT_STEAM_RUNS) {
    badges.push({ key: "steamMove", label: BADGE_LABELS.steamMove, tone: "interactive" });
  } else if (analysis?.sharp_movement_game_ids.includes(game.game_id)) {
    badges.push({ key: "sharpMove", label: BADGE_LABELS.sharpMove, tone: "interactive" });
  }

  if (analysis?.biggest_favorite_game_id === game.game_id && vegas.total_movement !== null && vegas.total_movement < 0) {
    badges.push({ key: "trapGame", label: BADGE_LABELS.trapGame, tone: "neutral" });
  }

  if (totalTier(vegas.current_home.total) === "low") badges.push({ key: "pitchersDuel", label: BADGE_LABELS.pitchersDuel, tone: "positive" });

  const homeMl = vegas.current_home.moneyline;
  const awayMl = vegas.current_away.moneyline;
  if (homeMl !== null && homeMl < 0) badges.push({ key: "homeFavorite", label: BADGE_LABELS.homeFavorite, tone: "neutral" });
  else if (awayMl !== null && awayMl < 0) badges.push({ key: "roadFavorite", label: BADGE_LABELS.roadFavorite, tone: "neutral" });

  return badges;
}

// ---------------------------------------------------------------------------
// AI Summary (deterministic templates -- no LLM, mirrors
// research/game_environment/summary.py's discipline exactly)
// ---------------------------------------------------------------------------

export function buildVegasAiSummary(game: GameEnvironmentReport, analysis: VegasSlateAnalysis | null): string[] {
  const vegas = game.vegas;
  if (!vegas || vegas.current_home.total === null) {
    return ["Vegas lines are unavailable for this game."];
  }
  const bullets: string[] = [];
  const tier = totalTier(vegas.current_home.total);
  if (tier === "high") bullets.push("Excellent hitting environment.");
  else if (tier === "low") bullets.push("Excellent pitcher's environment.");
  else bullets.push("Balanced offensive environment.");

  if (analysis?.highest_total_game_id === game.game_id) bullets.push("Highest implied total on the slate.");
  else if (analysis?.lowest_total_game_id === game.game_id) bullets.push("Lowest implied total on the slate.");

  if (vegas.total_movement !== null && Math.abs(vegas.total_movement) >= 0.1) {
    const magnitude = Math.abs(vegas.total_movement);
    const direction = vegas.total_movement > 0 ? "risen" : "fallen";
    bullets.push(`Total has ${direction} ${magnitude.toFixed(1)} run${magnitude === 1 ? "" : "s"}.`);
  }

  const isSharp = analysis?.sharp_movement_game_ids.includes(game.game_id) ?? false;
  if (isSharp && vegas.moneyline_movement_home !== null && vegas.moneyline_movement_home !== 0) {
    const side = vegas.moneyline_movement_home < 0 ? game.home_team : game.away_team;
    bullets.push(`Sharp money appears to be backing ${side}.`);
  }

  const conclusions = game.weather_analysis?.conclusions ?? [];
  bullets.push(conclusions.length === 0 ? "Weather neutral." : conclusions[0].text);

  const fatiguedSides = [
    { side: game.home_team, profile: game.bullpen_home },
    { side: game.away_team, profile: game.bullpen_away },
  ].filter((s) => s.profile?.estimated_fatigue === "high");
  if (fatiguedSides.length > 0) {
    bullets.push(`${fatiguedSides.map((s) => s.side).join("/")} bullpen fatigue favors late offense.`);
  }

  return bullets;
}

// ---------------------------------------------------------------------------
// Line movement series (mini sparkline). Milestone 24: for MOCK data,
// the mock Vegas provider seeds BOTH the opening total and the drift
// purely from game_id (vegas.py), so regenerating the report never
// changes either value -- the only two honest points are Opening and
// Current. For REAL data, buildRealTotalMovementSeries below reads
// EVERY saved Game Environment snapshot for the day (gameEnvironment.ts
// ::loadEnvironmentReportHistory) and plots this project's own genuine
// intraday history -- never fabricated intermediate points.
// ---------------------------------------------------------------------------

export interface LineMovementSeries {
  points: number[]; // [opening, current] for mock; every real observed total for real data
  open: number | null;
  current: number | null;
  highest: number | null;
  lowest: number | null;
}

export function buildTotalMovementSeries(vegas: VegasSnapshot | null): LineMovementSeries {
  const open = vegas?.opening_home?.total ?? null;
  const current = vegas?.current_home?.total ?? null;
  const points = [open, current].filter((v): v is number => v !== null);
  return {
    points,
    open,
    current,
    highest: points.length ? Math.max(...points) : null,
    lowest: points.length ? Math.min(...points) : null,
  };
}

/** Milestone 24: genuine intraday total-movement history for a REAL
 * (non-mock) game, built from every Game Environment snapshot this
 * project has actually saved today (oldest first) -- never a fabricated
 * intermediate point. Skips a snapshot entirely if this game's Vegas
 * data is missing, mock, or has no total at that point in time. Falls
 * back to the plain [opening, current] shape (buildTotalMovementSeries)
 * when fewer than 2 real observations exist. */
export function buildRealTotalMovementSeries(reports: SlateEnvironmentReport[], gameId: string): LineMovementSeries {
  const points: number[] = [];
  for (const report of reports) {
    const game = report.games.find((g) => g.game_id === gameId);
    const vegas = game?.vegas;
    if (!vegas || vegas.is_mock || vegas.current_home.total === null) continue;
    points.push(vegas.current_home.total);
  }
  if (points.length < 2) {
    const latestGame = reports.at(-1)?.games.find((g) => g.game_id === gameId);
    return buildTotalMovementSeries(latestGame?.vegas ?? null);
  }
  return {
    points,
    open: points[0],
    current: points[points.length - 1],
    highest: Math.max(...points),
    lowest: Math.min(...points),
  };
}

// ---------------------------------------------------------------------------
// Slate-wide summary cards
// ---------------------------------------------------------------------------

export interface VegasSummaryStats {
  gameCount: number;
  averageTotal: number | null;
  highestTotal: { value: number | null; game: GameEnvironmentReport | null };
  lowestTotal: { value: number | null; game: GameEnvironmentReport | null };
  biggestFavorite: { moneyline: number | null; team: string | null; game: GameEnvironmentReport | null };
  largestLineMove: { value: number | null; game: GameEnvironmentReport | null }; // largest |moneyline_movement_home|
  largestTotalMove: { value: number | null; game: GameEnvironmentReport | null };
  averageImpliedRuns: number | null;
}

function gameById(games: GameEnvironmentReport[], id: string | null | undefined): GameEnvironmentReport | null {
  if (!id) return null;
  return games.find((g) => g.game_id === id) ?? null;
}

export function buildVegasSummaryStats(report: SlateEnvironmentReport): VegasSummaryStats {
  const games = report.games;
  const withVegas = games.filter((g): g is GameEnvironmentReport & { vegas: VegasSnapshot } => g.vegas !== null);
  const analysis = report.vegas_slate_analysis;

  const totals = withVegas.map((g) => g.vegas.current_home.total).filter((v): v is number => v !== null);
  const averageTotal = totals.length ? totals.reduce((sum, v) => sum + v, 0) / totals.length : null;

  const impliedValues = withVegas.flatMap((g) => [g.vegas.home_implied_runs, g.vegas.away_implied_runs]).filter((v): v is number => v !== null);
  const averageImpliedRuns = impliedValues.length ? impliedValues.reduce((sum, v) => sum + v, 0) / impliedValues.length : null;

  const highestGame = gameById(games, analysis?.highest_total_game_id);
  const lowestGame = gameById(games, analysis?.lowest_total_game_id);
  const favoriteGame = gameById(games, analysis?.biggest_favorite_game_id);
  const totalMoveGame = gameById(games, analysis?.largest_movement_game_id);

  let favoriteMoneyline: number | null = null;
  let favoriteTeam: string | null = null;
  if (favoriteGame?.vegas) {
    const homeMl = favoriteGame.vegas.current_home.moneyline;
    const awayMl = favoriteGame.vegas.current_away.moneyline;
    if (homeMl !== null && (awayMl === null || homeMl < awayMl)) {
      favoriteMoneyline = homeMl;
      favoriteTeam = favoriteGame.home_team;
    } else if (awayMl !== null) {
      favoriteMoneyline = awayMl;
      favoriteTeam = favoriteGame.away_team;
    }
  }

  let largestLineMoveValue: number | null = null;
  let largestLineMoveGame: GameEnvironmentReport | null = null;
  for (const g of withVegas) {
    const move = g.vegas.moneyline_movement_home;
    if (move === null) continue;
    if (largestLineMoveValue === null || Math.abs(move) > Math.abs(largestLineMoveValue)) {
      largestLineMoveValue = move;
      largestLineMoveGame = g;
    }
  }

  return {
    gameCount: games.length,
    averageTotal,
    highestTotal: { value: highestGame?.vegas?.current_home.total ?? null, game: highestGame },
    lowestTotal: { value: lowestGame?.vegas?.current_home.total ?? null, game: lowestGame },
    biggestFavorite: { moneyline: favoriteMoneyline, team: favoriteTeam, game: favoriteGame },
    largestLineMove: { value: largestLineMoveValue, game: largestLineMoveGame },
    largestTotalMove: { value: totalMoveGame?.vegas?.total_movement ?? null, game: totalMoveGame },
    averageImpliedRuns,
  };
}

// ---------------------------------------------------------------------------
// Pitching matchup join. GameEnvironmentReport has no pitcher field at
// all -- Search-by-pitcher and the expanded row's "Pitching Matchup"
// need one, so the page (server component) joins the latest Pitcher
// Agent snapshot in by TEAM ABBREVIATION (every probable starter's own
// record already carries `team`), never by inventing a name.
// ---------------------------------------------------------------------------

export interface VegasGameRow {
  game: GameEnvironmentReport;
  homePitcher: PitcherRecord | null;
  awayPitcher: PitcherRecord | null;
}

export function buildVegasGameRows(games: GameEnvironmentReport[], pitchers: PitcherRecord[]): VegasGameRow[] {
  const byTeam = new Map<string, PitcherRecord>();
  for (const p of pitchers) {
    if (!byTeam.has(p.team)) byTeam.set(p.team, p);
  }
  return games.map((game) => ({
    game,
    homePitcher: byTeam.get(game.home_team) ?? null,
    awayPitcher: byTeam.get(game.away_team) ?? null,
  }));
}
