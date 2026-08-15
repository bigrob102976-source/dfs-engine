import type { AiPlayerProjection } from "./aiProjections";
import type { GameEnvironmentReport, SlateEnvironmentReport } from "./gameEnvironment";
import { weatherRiskValue } from "./environmentSortFilter";
import { buildStackSummaries, type StackSummary } from "./stacks";
import type { OwnershipSnapshot, TeamPopularity } from "./types";
import type { PlayerRow } from "./types";
import { deriveVegasBadges, vegasScore, type VegasBadge } from "./vegasIntelligence";

// Milestone: AI Slate Command Center. This module is a pure, read-only
// COMPOSITION layer -- every number here is read straight from already
// -built snapshots (Game Environment, Pitcher/Batter Agent, Ownership,
// Stacks) or is a trivial derived transform of them (an average, a
// ratio, a sort). It never recomputes a projection, a score, or an
// ownership value, and it never touches Pitcher/Batter Agent,
// Optimizer, Ownership Model, research scoring, or the External
// Projection/CSV Import/Weather/Vegas Intelligence frameworks.

// ---------------------------------------------------------------------------
// KPI cards
// ---------------------------------------------------------------------------

export interface SlateKpi {
  key: string;
  label: string;
  value: string | number;
  /** Present only for genuinely numeric cards (Games, scores, totals,
   * movement) -- lets the UI layer animate a count-up. Text identity
   * cards (a team/player name) omit it and render `value` directly. */
  numeric?: number | null;
  sub?: string;
  tone?: "positive" | "negative" | "neutral";
}

function fmt1(v: number | null | undefined): string {
  return v === null || v === undefined ? "--" : v.toFixed(1);
}

function matchup(game: GameEnvironmentReport | null): string | undefined {
  return game ? `${game.away_team} @ ${game.home_team}` : undefined;
}

/** points per $1,000 salary -- the standard DFS "value" ratio. Purely a
 * different presentation of two fields the pipeline already computed
 * (projection, salary); never a new projection. */
export function valueScore(row: PlayerRow): number | null {
  if (row.projection === null || row.salary === null || row.salary <= 0) return null;
  return (row.projection / row.salary) * 1000;
}

export interface ValuedStack extends StackSummary {
  value: number | null; // averageProjection per $1,000 of the stack's own top5 average salary
}

/** Ranks stacks by DFS value (projection per $1k) using each stack's
 * already-computed top5 rows -- StackSummary itself carries no salary
 * field, so this derives value from the same top5 PlayerRow data the
 * stack summary already returned, never inventing a new number. */
export function rankStacksByValue(stacks: StackSummary[]): ValuedStack[] {
  return stacks
    .map((s) => {
      const salaries = s.top5.map((p) => p.salary).filter((v): v is number => v !== null);
      const avgSalary = salaries.length ? salaries.reduce((sum, v) => sum + v, 0) / salaries.length : null;
      const value = s.averageProjection !== null && avgSalary ? (s.averageProjection / avgSalary) * 1000 : null;
      return { ...s, value };
    })
    .sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
}

export function rankPlayersByValue(rows: PlayerRow[]): Array<PlayerRow & { value: number | null }> {
  return rows.map((r) => ({ ...r, value: valueScore(r) })).sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
}

function highestOwnedTeam(ownership: OwnershipSnapshot | null): { team: string; popularity: TeamPopularity } | null {
  if (!ownership) return null;
  const entries = Object.values(ownership.team_popularity ?? {});
  if (entries.length === 0) return null;
  const top = entries.reduce((best, cur) => (cur.team_popularity_score > best.team_popularity_score ? cur : best));
  return { team: top.team, popularity: top };
}

export interface SlateKpiInputs {
  report: SlateEnvironmentReport | null;
  ownership: OwnershipSnapshot | null;
  pitcherRows: PlayerRow[];
  stacks: StackSummary[];
}

/** The 13 top KPI cards. Every value traces to an already-built
 * snapshot; see the inline comment on each for its exact source. */
export function buildSlateKpis({ report, ownership, pitcherRows, stacks }: SlateKpiInputs): SlateKpi[] {
  const games = report?.games ?? [];
  const withVegas = games.filter((g) => g.vegas !== null);
  const analysis = report?.vegas_slate_analysis ?? null;

  const highestTotalGame = analysis?.highest_total_game_id ? (games.find((g) => g.game_id === analysis.highest_total_game_id) ?? null) : null;
  const lowestTotalGame = analysis?.lowest_total_game_id ? (games.find((g) => g.game_id === analysis.lowest_total_game_id) ?? null) : null;

  const bestHitting = games.reduce<GameEnvironmentReport | null>(
    (best, g) => (best === null || g.environment_score.hitter > best.environment_score.hitter ? g : best),
    null,
  );
  const bestPitching = games.reduce<GameEnvironmentReport | null>(
    (best, g) => (best === null || g.environment_score.pitcher > best.environment_score.pitcher ? g : best),
    null,
  );

  const topStack = stacks[0] ?? null;
  const valuedStacks = rankStacksByValue(stacks);
  const bestValueStack = valuedStacks.find((s) => s.value !== null) ?? null;

  const topPitcher = [...pitcherRows].sort((a, b) => (b.projection ?? -1) - (a.projection ?? -1))[0] ?? null;
  const valuedPitchers = rankPlayersByValue(pitcherRows);
  const bestValuePitcher = valuedPitchers.find((p) => p.value !== null) ?? null;

  const topOwnedTeam = highestOwnedTeam(ownership);

  let largestMoveGame: GameEnvironmentReport | null = null;
  for (const g of withVegas) {
    const move = g.vegas!.total_movement;
    if (move === null) continue;
    if (largestMoveGame === null || Math.abs(move) > Math.abs(largestMoveGame.vegas!.total_movement ?? 0)) largestMoveGame = g;
  }

  let weatherRiskGame: GameEnvironmentReport | null = null;
  let weatherRiskValueTop: number | null = null;
  for (const g of games) {
    const risk = weatherRiskValue(g);
    if (risk === null) continue;
    if (weatherRiskValueTop === null || risk > weatherRiskValueTop) {
      weatherRiskValueTop = risk;
      weatherRiskGame = g;
    }
  }

  const overallScores = games.map((g) => g.environment_score.overall);
  const averageSlateScore = overallScores.length ? overallScores.reduce((sum, v) => sum + v, 0) / overallScores.length : null;

  const largestMoveValue = largestMoveGame?.vegas?.total_movement ?? null;

  return [
    { key: "games", label: "Games", value: games.length, numeric: games.length },
    { key: "highestTotal", label: "Highest Total", value: fmt1(highestTotalGame?.vegas?.current_home.total), numeric: highestTotalGame?.vegas?.current_home.total ?? null, sub: matchup(highestTotalGame), tone: "negative" },
    { key: "lowestTotal", label: "Lowest Total", value: fmt1(lowestTotalGame?.vegas?.current_home.total), numeric: lowestTotalGame?.vegas?.current_home.total ?? null, sub: matchup(lowestTotalGame), tone: "positive" },
    { key: "bestHitting", label: "Best Hitting Environment", value: bestHitting ? bestHitting.environment_score.hitter.toFixed(0) : "--", numeric: bestHitting ? bestHitting.environment_score.hitter : null, sub: matchup(bestHitting) },
    { key: "bestPitching", label: "Best Pitching Environment", value: bestPitching ? bestPitching.environment_score.pitcher.toFixed(0) : "--", numeric: bestPitching ? bestPitching.environment_score.pitcher : null, sub: matchup(bestPitching) },
    { key: "topStack", label: "Top Stack", value: topStack ? topStack.team : "--", sub: topStack ? `${fmt1(topStack.averageProjection)} proj/player` : undefined },
    { key: "bestValueStack", label: "Best Value Stack", value: bestValueStack ? bestValueStack.team : "--", sub: bestValueStack?.value != null ? `${bestValueStack.value.toFixed(2)} pts/$1k` : undefined },
    { key: "topPitcher", label: "Top Pitcher", value: topPitcher ? topPitcher.name : "--", sub: topPitcher ? `${fmt1(topPitcher.projection)} pts` : undefined },
    { key: "bestValuePitcher", label: "Best Value Pitcher", value: bestValuePitcher ? bestValuePitcher.name : "--", sub: bestValuePitcher?.value != null ? `${bestValuePitcher.value.toFixed(2)} pts/$1k` : undefined },
    {
      key: "highestOwnedStack",
      label: "Highest Owned Stack",
      value: topOwnedTeam ? topOwnedTeam.team : "--",
      sub: topOwnedTeam ? `${topOwnedTeam.popularity.aggregate_projected_ownership.toFixed(0)}% agg. own` : undefined,
    },
    {
      key: "largestVegasMove",
      label: "Largest Vegas Move",
      value: largestMoveValue !== null ? `${largestMoveValue > 0 ? "+" : ""}${largestMoveValue.toFixed(1)}` : "--",
      numeric: largestMoveValue,
      sub: matchup(largestMoveGame),
      tone: largestMoveValue ? (largestMoveValue > 0 ? "positive" : "negative") : "neutral",
    },
    {
      key: "weatherRiskGame",
      label: "Weather Risk Game",
      value: weatherRiskValueTop !== null ? weatherRiskValueTop.toFixed(0) : "--",
      numeric: weatherRiskValueTop,
      sub: matchup(weatherRiskGame),
      tone: weatherRiskValueTop && weatherRiskValueTop >= 25 ? "negative" : "neutral",
    },
    { key: "averageSlateScore", label: "Average Slate Score", value: averageSlateScore !== null ? averageSlateScore.toFixed(0) : "--", numeric: averageSlateScore },
  ];
}

// ---------------------------------------------------------------------------
// Slate Rankings (one row per game, ranked by a combined score)
// ---------------------------------------------------------------------------

export type SlateRankingBadgeKey = VegasBadge["key"] | "windOut" | "leverage";

export interface SlateRankingBadge {
  key: SlateRankingBadgeKey;
  label: string;
  tone: "positive" | "negative" | "neutral" | "interactive";
}

export interface GameRanking {
  game: GameEnvironmentReport;
  vegasScoreValue: number | null;
  environmentScore: number;
  weatherScore: number | null;
  stackScore: number;
  ownershipScore: number | null;
  combinedScore: number;
  badges: SlateRankingBadge[];
}

/** Wind blowing out at a notable/strong strength, per
 * research/game_environment/weather.py's conclusion codes -- a pure
 * reuse of already-generated conclusion text, not a new wind
 * classification. */
function hasWindOut(game: GameEnvironmentReport): boolean {
  return (game.weather_analysis?.conclusions ?? []).some((c) => c.code.startsWith("wind") && c.code.endsWith("out"));
}

const LEVERAGE_OWNERSHIP_CEILING = 40; // 0-100 scale team_popularity_score
const LEVERAGE_STACK_FLOOR = 60; // 0-100 scale environment_score.stack

function ownershipScoreFor(game: GameEnvironmentReport, ownership: OwnershipSnapshot | null): number | null {
  if (!ownership) return null;
  const home = ownership.team_popularity[game.home_team]?.team_popularity_score;
  const away = ownership.team_popularity[game.away_team]?.team_popularity_score;
  const values = [home, away].filter((v): v is number => v !== undefined && v !== null);
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function buildGameRankings(report: SlateEnvironmentReport | null, ownership: OwnershipSnapshot | null): GameRanking[] {
  const games = report?.games ?? [];
  const analysis = report?.vegas_slate_analysis ?? null;

  const rankings: GameRanking[] = games.map((game) => {
    const vsc = vegasScore(game.vegas?.current_home?.total);
    const environmentScore = game.environment_score.overall;
    const risk = weatherRiskValue(game);
    const weatherScore = risk === null ? null : 100 - risk;
    const stackScore = game.environment_score.stack;
    const ownershipScore = ownershipScoreFor(game, ownership);

    const components = [vsc, environmentScore, weatherScore, stackScore, ownershipScore].filter((v): v is number => v !== null);
    const combinedScore = components.length ? components.reduce((sum, v) => sum + v, 0) / components.length : 0;

    const badges: SlateRankingBadge[] = deriveVegasBadges(game, analysis).map((b) => ({ key: b.key, label: b.label, tone: b.tone }));
    if (hasWindOut(game)) badges.push({ key: "windOut", label: "Wind Out", tone: "positive" });
    if (ownershipScore !== null && ownershipScore <= LEVERAGE_OWNERSHIP_CEILING && stackScore >= LEVERAGE_STACK_FLOOR) {
      badges.push({ key: "leverage", label: "Leverage", tone: "interactive" });
    }

    return { game, vegasScoreValue: vsc, environmentScore, weatherScore, stackScore, ownershipScore, combinedScore, badges };
  });

  return rankings.sort((a, b) => b.combinedScore - a.combinedScore);
}

// ---------------------------------------------------------------------------
// Deterministic AI Slate Summary (no LLM -- template bullets over
// already-computed thresholds, same discipline as
// research/game_environment/summary.py and
// lib/vegasIntelligence.ts::buildVegasAiSummary)
// ---------------------------------------------------------------------------

export interface AiSlateSummaryInputs {
  report: SlateEnvironmentReport | null;
  ownership: OwnershipSnapshot | null;
  pitcherRows: PlayerRow[];
  hitterRows: PlayerRow[];
  stacks: StackSummary[];
}

export function buildSlateAiSummary({ report, ownership, pitcherRows, hitterRows, stacks }: AiSlateSummaryInputs): string[] {
  const bullets: string[] = [];
  const games = report?.games ?? [];

  if (games.length === 0) return ["No slate data available yet -- refresh today's research to generate an AI summary."];

  bullets.push(`Today's slate features ${games.length} game${games.length === 1 ? "" : "s"}.`);

  const bestHitting = games.reduce((best, g) => (g.environment_score.hitter > best.environment_score.hitter ? g : best));
  bullets.push(`${bestHitting.home_team} projects as the highest scoring offense.`);

  const topPitcher = [...pitcherRows].sort((a, b) => (b.projection ?? -1) - (a.projection ?? -1))[0];
  if (topPitcher) bullets.push(`${topPitcher.name} leads all pitchers.`);

  const analysis = report?.vegas_slate_analysis ?? null;
  const risenCount = games.filter((g) => (g.vegas?.total_movement ?? 0) > 0).length;
  if (risenCount > 0) bullets.push(`Vegas has increased totals in ${risenCount} game${risenCount === 1 ? "" : "s"}.`);
  const sharpCount = analysis?.sharp_movement_game_ids.length ?? 0;
  if (sharpCount > 0) bullets.push(`Sharp line movement detected in ${sharpCount} game${sharpCount === 1 ? "" : "s"}.`);

  const windOutGames = games.filter(hasWindOut);
  if (windOutGames.length > 0) bullets.push(`Wind is favorable in ${windOutGames.map((g) => g.venue_name ?? g.home_team).join(", ")}.`);

  const topOwned = highestOwnedTeam(ownership);
  if (topOwned) bullets.push(`Ownership appears concentrated on the ${topOwned.team}.`);

  const leverageStacks = stacks
    .filter((s) => ownership && (ownership.team_popularity[s.team]?.team_popularity_score ?? 100) <= LEVERAGE_OWNERSHIP_CEILING)
    .filter((s) => (s.averageProjection ?? 0) > 0)
    .slice(0, 3);
  if (leverageStacks.length > 0) bullets.push(`Top leverage stacks include ${leverageStacks.map((s) => s.team).join(" and ")}.`);

  const pitcherDuelGames = games.filter((g) => (g.vegas?.current_home?.total ?? 99) <= 7.5);
  if (pitcherDuelGames.length > 0) {
    bullets.push("Cash games project around balanced pitching.");
  }
  bullets.push("Large-field tournaments favor lower-owned stacks.");

  const lowestTotalGame = analysis?.lowest_total_game_id ? games.find((g) => g.game_id === analysis.lowest_total_game_id) : null;
  if (lowestTotalGame?.vegas?.current_home?.total !== undefined && lowestTotalGame?.vegas?.current_home?.total !== null) {
    bullets.push(`Lowest implied total on the slate is ${lowestTotalGame.vegas.current_home.total.toFixed(1)} (${lowestTotalGame.away_team} @ ${lowestTotalGame.home_team}).`);
  }

  const topLeveragePlayer = [...hitterRows, ...pitcherRows].reduce<PlayerRow | null>(
    (best, r) => (r.leverage !== null && (best === null || (best.leverage ?? -Infinity) < r.leverage) ? r : best),
    null,
  );
  if (topLeveragePlayer) bullets.push(`Greatest leverage opportunity: ${topLeveragePlayer.name} (${topLeveragePlayer.team}).`);

  return bullets;
}

// ---------------------------------------------------------------------------
// Line movement feed / risers & fallers / upcoming lock times
// ---------------------------------------------------------------------------

export interface LineMovementEntry {
  game: GameEnvironmentReport;
  movement: number;
}

/** Reuses each game's already-computed total_movement -- "risers" and
 * "fallers" here describe GAME totals (the only movement signal the
 * snapshot actually stores), not individual player projections; no
 * player-level trend/history exists anywhere in this codebase to derive
 * from without inventing one. */
export function buildLineMovementFeed(report: SlateEnvironmentReport | null): { risers: LineMovementEntry[]; fallers: LineMovementEntry[]; feed: LineMovementEntry[] } {
  const games = report?.games ?? [];
  const moved = games
    .filter((g) => g.vegas?.total_movement !== null && g.vegas?.total_movement !== undefined && g.vegas.total_movement !== 0)
    .map((g) => ({ game: g, movement: g.vegas!.total_movement! }));

  const risers = moved.filter((m) => m.movement > 0).sort((a, b) => b.movement - a.movement);
  const fallers = moved.filter((m) => m.movement < 0).sort((a, b) => a.movement - b.movement);
  const feed = [...moved].sort((a, b) => Math.abs(b.movement) - Math.abs(a.movement));

  return { risers, fallers, feed };
}

export interface LockTimeEntry {
  game: GameEnvironmentReport;
  gameDatetimeUtc: string;
}

export function buildUpcomingLockTimes(report: SlateEnvironmentReport | null): LockTimeEntry[] {
  const games = report?.games ?? [];
  return games
    .filter((g): g is GameEnvironmentReport & { game_datetime_utc: string } => Boolean(g.game_datetime_utc))
    .map((g) => ({ game: g, gameDatetimeUtc: g.game_datetime_utc }))
    .sort((a, b) => new Date(a.gameDatetimeUtc).getTime() - new Date(b.gameDatetimeUtc).getTime());
}

// ---------------------------------------------------------------------------
// Milestone 20: AI Projection Engine -- Command Center / Game Center
// rankings. Every field here is joined straight from the immutable
// ai_projection_*.json snapshot (projection_engine/scoring.py's output,
// see lib/aiProjections.ts) onto the SAME PlayerRow data already loaded
// for the rest of the page; nothing here recomputes a signal or a
// projection.
// ---------------------------------------------------------------------------

export interface AiRankedPlayer extends PlayerRow {
  aiProjection: number | null;
  aiDelta: number | null; // total_adjustment: aiProjection - independent projection
  aiConfidence: number | null;
  aiRisk: number | null;
  aiGrade: string | null;
}

/** Joins the AI Projection Engine's per-player output onto already
 * -loaded PlayerRows by id (the mlb player_id both sides key on). A
 * player with no AI Projection snapshot entry yet simply carries null
 * AI fields -- never a fabricated value. */
export function joinAiProjections(rows: PlayerRow[], aiByPlayerId: Map<string, AiPlayerProjection>): AiRankedPlayer[] {
  return rows.map((r) => {
    const ai = aiByPlayerId.get(r.id);
    return {
      ...r,
      aiProjection: ai?.ai_projection ?? null,
      aiDelta: ai?.total_adjustment ?? null,
      aiConfidence: ai?.ai_confidence ?? null,
      aiRisk: ai?.ai_risk ?? null,
      aiGrade: ai?.ai_grade ?? null,
    };
  });
}

function aiValueScore(row: AiRankedPlayer): number | null {
  if (row.aiProjection === null || row.salary === null || row.salary <= 0) return null;
  return Math.round((row.aiProjection / row.salary) * 1000 * 100) / 100;
}

export interface AiValuedPlayer extends AiRankedPlayer {
  aiValue: number | null;
}

/** Top N players by AI Projection per $1,000 salary -- same "value"
 * convention as this module's own rankPlayersByValue, applied to the AI
 * tier instead of the independent one. */
export function topAiValues(rows: AiRankedPlayer[], limit = 10): AiValuedPlayer[] {
  return rows
    .map((r) => ({ ...r, aiValue: aiValueScore(r) }))
    .filter((r): r is AiValuedPlayer => r.aiValue !== null)
    .sort((a, b) => (b.aiValue ?? 0) - (a.aiValue ?? 0))
    .slice(0, limit);
}

/** Players the AI Projection Engine moved UP the most from their
 * independent baseline. */
export function largestAiUpgrades(rows: AiRankedPlayer[], limit = 10): AiRankedPlayer[] {
  return rows
    .filter((r) => r.aiDelta !== null && r.aiDelta > 0)
    .sort((a, b) => (b.aiDelta ?? 0) - (a.aiDelta ?? 0))
    .slice(0, limit);
}

/** Players the AI Projection Engine moved DOWN the most from their
 * independent baseline. */
export function largestAiDowngrades(rows: AiRankedPlayer[], limit = 10): AiRankedPlayer[] {
  return rows
    .filter((r) => r.aiDelta !== null && r.aiDelta < 0)
    .sort((a, b) => (a.aiDelta ?? 0) - (b.aiDelta ?? 0))
    .slice(0, limit);
}

export function highestAiConfidence(rows: AiRankedPlayer[], limit = 10): AiRankedPlayer[] {
  return rows
    .filter((r) => r.aiConfidence !== null)
    .sort((a, b) => (b.aiConfidence ?? 0) - (a.aiConfidence ?? 0))
    .slice(0, limit);
}

export function lowestAiConfidence(rows: AiRankedPlayer[], limit = 10): AiRankedPlayer[] {
  return rows
    .filter((r) => r.aiConfidence !== null)
    .sort((a, b) => (a.aiConfidence ?? 0) - (b.aiConfidence ?? 0))
    .slice(0, limit);
}

/** Team stack summaries built from AI Projections instead of independent
 * ones -- reuses lib/stacks.ts::buildStackSummaries UNCHANGED by simply
 * substituting `projection` with `aiProjection` before calling it, so
 * the team-averaging/top5 logic is never duplicated. */
export function buildAiStackSummaries(hitterRows: AiRankedPlayer[], teamPopularity: Record<string, TeamPopularity>): StackSummary[] {
  const asIndependentShaped: PlayerRow[] = hitterRows.map((r) => ({ ...r, projection: r.aiProjection }));
  return buildStackSummaries(asIndependentShaped, teamPopularity);
}
