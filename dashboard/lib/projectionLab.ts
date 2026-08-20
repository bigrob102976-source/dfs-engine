import type { AiPlayerProjection } from "./aiProjections";
import { joinAiProjections, joinNativeProjections } from "./commandCenter";
import type { ProjectionComparisonRow } from "./externalProjections";
import type { FantasyProsPlayerProjection } from "./fantasyProsProjections";
import type { NativePlayerProjection } from "./nativeProjections";
import type { PlayerRow } from "./types";

// Milestone 27 -- Part 3: PROJECTION LAB. Pure composition layer, same
// discipline as lib/commandCenter.ts -- every field here is read
// straight from an already-built, already-immutable snapshot (BlueCollar
// import, Native Projection, AI Projection, actual DK results) or is a
// trivial derived transform (a subtraction). Nothing here recomputes a
// projection or invents a value; a source with no data for a player
// stays null, rendered as "NOT LOADED"/"--" by the page, never a guess.

export interface ProjectionLabRow {
  id: string;
  name: string;
  team: string;
  opponent: string | null;
  gameId: string | null;
  playerType: "pitcher" | "hitter";
  position: string | null;
  salary: number | null;
  ownership: number | null;
  leverage: number | null;

  blueCollarProjection: number | null;
  nativeProjection: number | null;
  nativeConfidence: number | null;
  aiProjection: number | null;
  aiConfidence: number | null;

  // FantasyPros integration: a COMPARISON + OPTIONAL OPTIMIZER SOURCE
  // only -- never fed into Native/AI's own computation (see
  // lib/fantasyProsProjections.ts's module docstring).
  fantasyProsProjection: number | null;
  fantasyProsMatchStatus: "matched" | "unmatched" | "ambiguous" | null;

  aiVsNativeDelta: number | null; // Big Money AI - Big Money Native
  bigMoneyVsBlueCollarDelta: number | null; // Big Money AI (or Native if AI unavailable) - BlueCollar
  fpVsNativeDelta: number | null; // FantasyPros - Big Money Native
  fpVsAiDelta: number | null; // FantasyPros - Big Money AI
  bigMoneyVsFantasyProsDelta: number | null; // Big Money AI (or Native if AI unavailable) - FantasyPros

  actualDkPoints: number | null; // null until postgame results exist

  // Milestone 30.1: carried through so projection coverage can be
  // measured against confirmed starters specifically, not just every
  // preserved DK row (a relief-pitcher-heavy slate shouldn't make
  // coverage look artificially poor -- see buildProjectionLabSummary).
  eligibilityStatus: string | null;
  optimizerEligible: boolean;
}

function delta(a: number | null, b: number | null): number | null {
  return a !== null && b !== null ? Math.round((a - b) * 100) / 100 : null;
}

export function buildProjectionLabRows(
  rows: PlayerRow[],
  externalByPlayerId: Map<string, ProjectionComparisonRow>,
  nativeByPlayerId: Map<string, NativePlayerProjection>,
  aiByPlayerId: Map<string, AiPlayerProjection>,
  actualByPlayerId: Map<string, number>,
  fantasyProsByPlayerId: Map<string, FantasyProsPlayerProjection> = new Map(),
): ProjectionLabRow[] {
  const nativeById = new Map(joinNativeProjections(rows, nativeByPlayerId).map((r) => [r.id, r]));
  const aiById = new Map(joinAiProjections(rows, aiByPlayerId).map((r) => [r.id, r]));

  return rows.map((r) => {
    const native = nativeById.get(r.id) ?? null;
    const ai = aiById.get(r.id) ?? null;
    const nativeProjection = native?.nativeProjection ?? null;
    const aiProjection = ai?.aiProjection ?? null;
    const blueCollarProjection = externalByPlayerId.get(r.id)?.externalProjection ?? null;
    const fantasyPros = fantasyProsByPlayerId.get(r.id) ?? null;
    const fantasyProsProjection = fantasyPros?.dk_points ?? null;
    const bigMoneyFinal = aiProjection ?? nativeProjection;
    return {
      id: r.id,
      name: r.name,
      team: r.team,
      opponent: r.opponent,
      gameId: r.gameId,
      playerType: r.playerType,
      position: r.position,
      salary: r.salary,
      ownership: r.ownership,
      leverage: r.leverage,
      blueCollarProjection,
      nativeProjection,
      nativeConfidence: native?.nativeConfidence ?? null,
      aiProjection,
      aiConfidence: ai?.aiConfidence ?? null,
      fantasyProsProjection,
      fantasyProsMatchStatus: fantasyPros?.match_status ?? null,
      aiVsNativeDelta: delta(aiProjection, nativeProjection),
      bigMoneyVsBlueCollarDelta: delta(bigMoneyFinal, blueCollarProjection),
      fpVsNativeDelta: delta(fantasyProsProjection, nativeProjection),
      fpVsAiDelta: delta(fantasyProsProjection, aiProjection),
      bigMoneyVsFantasyProsDelta: delta(bigMoneyFinal, fantasyProsProjection),
      actualDkPoints: actualByPlayerId.get(r.id) ?? null,
      eligibilityStatus: r.eligibilityStatus,
      optimizerEligible: r.optimizerEligible,
    };
  });
}

export interface ProjectionLabSummary {
  players: number; // every preserved DK row, regardless of eligibility
  // Milestone 30.1: confirmed starters only (optimizerEligible) -- the
  // denominator that actually matters for projection-model coverage.
  // Hundreds of relief pitchers/bench hitters must never make coverage
  // look artificially poor.
  eligiblePlayers: number;
  blueCollarCoverage: number; // count with a BlueCollar value (all preserved rows)
  nativeCoverage: number;
  aiCoverage: number;
  nativeEligibleCoverage: number; // native coverage among eligiblePlayers only
  aiEligibleCoverage: number; // AI coverage among eligiblePlayers only
  // FantasyPros: coverage measured against eligiblePlayers only (per
  // this integration's own "must not show every FantasyPros player"
  // instruction) -- there is no separate "all preserved rows" FantasyPros
  // coverage figure, unlike blueCollarCoverage/nativeCoverage/aiCoverage.
  fantasyProsCoverage: number;
  averageNativeProjection: number | null;
  averageAiProjection: number | null;
  averageFantasyProsProjection: number | null;
  averageAiAdjustment: number | null; // average (aiProjection - nativeProjection) where both exist
  largestAiUpgrade: ProjectionLabRow | null;
  largestAiDowngrade: ProjectionLabRow | null;
  largestBigMoneyVsBlueCollarDifference: ProjectionLabRow | null;
  largestBigMoneyOverFantasyPros: ProjectionLabRow | null; // biggest positive (Big Money AI/Native) - FantasyPros
  largestBigMoneyUnderFantasyPros: ProjectionLabRow | null; // biggest negative (Big Money AI/Native) - FantasyPros
}

export function buildProjectionLabSummary(rows: ProjectionLabRow[]): ProjectionLabSummary {
  const blueCollarCoverage = rows.filter((r) => r.blueCollarProjection !== null).length;
  const nativeCoverage = rows.filter((r) => r.nativeProjection !== null).length;
  const aiCoverage = rows.filter((r) => r.aiProjection !== null).length;

  const eligibleRows = rows.filter((r) => r.optimizerEligible);
  const nativeEligibleCoverage = eligibleRows.filter((r) => r.nativeProjection !== null).length;
  const aiEligibleCoverage = eligibleRows.filter((r) => r.aiProjection !== null).length;
  const fantasyProsCoverage = eligibleRows.filter((r) => r.fantasyProsProjection !== null).length;

  const avg = (values: number[]): number | null => (values.length ? Math.round((values.reduce((s, v) => s + v, 0) / values.length) * 100) / 100 : null);
  const averageNativeProjection = avg(rows.map((r) => r.nativeProjection).filter((v): v is number => v !== null));
  const averageAiProjection = avg(rows.map((r) => r.aiProjection).filter((v): v is number => v !== null));
  const averageFantasyProsProjection = avg(rows.map((r) => r.fantasyProsProjection).filter((v): v is number => v !== null));

  const aiDeltas = rows.map((r) => r.aiVsNativeDelta).filter((v): v is number => v !== null);
  const averageAiAdjustment = aiDeltas.length ? Math.round((aiDeltas.reduce((s, v) => s + v, 0) / aiDeltas.length) * 100) / 100 : null;

  const withAiDelta = rows.filter((r) => r.aiVsNativeDelta !== null);
  const largestAiUpgrade = withAiDelta.length ? withAiDelta.reduce((best, r) => (r.aiVsNativeDelta! > best.aiVsNativeDelta! ? r : best)) : null;
  const largestAiDowngrade = withAiDelta.length ? withAiDelta.reduce((best, r) => (r.aiVsNativeDelta! < best.aiVsNativeDelta! ? r : best)) : null;

  const withBcDelta = rows.filter((r) => r.bigMoneyVsBlueCollarDelta !== null);
  const largestBigMoneyVsBlueCollarDifference = withBcDelta.length
    ? withBcDelta.reduce((best, r) => (Math.abs(r.bigMoneyVsBlueCollarDelta!) > Math.abs(best.bigMoneyVsBlueCollarDelta!) ? r : best))
    : null;

  const withFpDelta = rows.filter((r) => r.bigMoneyVsFantasyProsDelta !== null);
  const positiveFpDeltas = withFpDelta.filter((r) => r.bigMoneyVsFantasyProsDelta! > 0);
  const negativeFpDeltas = withFpDelta.filter((r) => r.bigMoneyVsFantasyProsDelta! < 0);
  const largestBigMoneyOverFantasyPros = positiveFpDeltas.length
    ? positiveFpDeltas.reduce((best, r) => (r.bigMoneyVsFantasyProsDelta! > best.bigMoneyVsFantasyProsDelta! ? r : best))
    : null;
  const largestBigMoneyUnderFantasyPros = negativeFpDeltas.length
    ? negativeFpDeltas.reduce((best, r) => (r.bigMoneyVsFantasyProsDelta! < best.bigMoneyVsFantasyProsDelta! ? r : best))
    : null;

  return {
    players: rows.length,
    eligiblePlayers: eligibleRows.length,
    blueCollarCoverage,
    nativeCoverage,
    aiCoverage,
    nativeEligibleCoverage,
    aiEligibleCoverage,
    fantasyProsCoverage,
    averageNativeProjection,
    averageAiProjection,
    averageFantasyProsProjection,
    averageAiAdjustment,
    largestAiUpgrade: largestAiUpgrade && largestAiUpgrade.aiVsNativeDelta! > 0 ? largestAiUpgrade : null,
    largestAiDowngrade: largestAiDowngrade && largestAiDowngrade.aiVsNativeDelta! < 0 ? largestAiDowngrade : null,
    largestBigMoneyVsBlueCollarDifference,
    largestBigMoneyOverFantasyPros,
    largestBigMoneyUnderFantasyPros,
  };
}
