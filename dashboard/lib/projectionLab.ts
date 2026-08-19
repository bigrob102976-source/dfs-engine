import type { AiPlayerProjection } from "./aiProjections";
import { joinAiProjections, joinNativeProjections } from "./commandCenter";
import type { ProjectionComparisonRow } from "./externalProjections";
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

  aiVsNativeDelta: number | null; // Big Money AI - Big Money Native
  bigMoneyVsBlueCollarDelta: number | null; // Big Money AI (or Native if AI unavailable) - BlueCollar

  actualDkPoints: number | null; // null until postgame results exist

  // Milestone 30.1: carried through so projection coverage can be
  // measured against confirmed starters specifically, not just every
  // preserved DK row (a relief-pitcher-heavy slate shouldn't make
  // coverage look artificially poor -- see buildProjectionLabSummary).
  eligibilityStatus: string | null;
  optimizerEligible: boolean;
}

export function buildProjectionLabRows(
  rows: PlayerRow[],
  externalByPlayerId: Map<string, ProjectionComparisonRow>,
  nativeByPlayerId: Map<string, NativePlayerProjection>,
  aiByPlayerId: Map<string, AiPlayerProjection>,
  actualByPlayerId: Map<string, number>,
): ProjectionLabRow[] {
  const nativeById = new Map(joinNativeProjections(rows, nativeByPlayerId).map((r) => [r.id, r]));
  const aiById = new Map(joinAiProjections(rows, aiByPlayerId).map((r) => [r.id, r]));

  return rows.map((r) => {
    const native = nativeById.get(r.id) ?? null;
    const ai = aiById.get(r.id) ?? null;
    const nativeProjection = native?.nativeProjection ?? null;
    const aiProjection = ai?.aiProjection ?? null;
    const blueCollarProjection = externalByPlayerId.get(r.id)?.externalProjection ?? null;
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
      aiVsNativeDelta: aiProjection !== null && nativeProjection !== null ? Math.round((aiProjection - nativeProjection) * 100) / 100 : null,
      bigMoneyVsBlueCollarDelta: bigMoneyFinal !== null && blueCollarProjection !== null ? Math.round((bigMoneyFinal - blueCollarProjection) * 100) / 100 : null,
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
  averageNativeProjection: number | null;
  averageAiAdjustment: number | null; // average (aiProjection - nativeProjection) where both exist
  largestAiUpgrade: ProjectionLabRow | null;
  largestAiDowngrade: ProjectionLabRow | null;
  largestBigMoneyVsBlueCollarDifference: ProjectionLabRow | null;
}

export function buildProjectionLabSummary(rows: ProjectionLabRow[]): ProjectionLabSummary {
  const blueCollarCoverage = rows.filter((r) => r.blueCollarProjection !== null).length;
  const nativeCoverage = rows.filter((r) => r.nativeProjection !== null).length;
  const aiCoverage = rows.filter((r) => r.aiProjection !== null).length;

  const eligibleRows = rows.filter((r) => r.optimizerEligible);
  const nativeEligibleCoverage = eligibleRows.filter((r) => r.nativeProjection !== null).length;
  const aiEligibleCoverage = eligibleRows.filter((r) => r.aiProjection !== null).length;

  const nativeValues = rows.map((r) => r.nativeProjection).filter((v): v is number => v !== null);
  const averageNativeProjection = nativeValues.length ? Math.round((nativeValues.reduce((s, v) => s + v, 0) / nativeValues.length) * 100) / 100 : null;

  const aiDeltas = rows.map((r) => r.aiVsNativeDelta).filter((v): v is number => v !== null);
  const averageAiAdjustment = aiDeltas.length ? Math.round((aiDeltas.reduce((s, v) => s + v, 0) / aiDeltas.length) * 100) / 100 : null;

  const withAiDelta = rows.filter((r) => r.aiVsNativeDelta !== null);
  const largestAiUpgrade = withAiDelta.length ? withAiDelta.reduce((best, r) => (r.aiVsNativeDelta! > best.aiVsNativeDelta! ? r : best)) : null;
  const largestAiDowngrade = withAiDelta.length ? withAiDelta.reduce((best, r) => (r.aiVsNativeDelta! < best.aiVsNativeDelta! ? r : best)) : null;

  const withBcDelta = rows.filter((r) => r.bigMoneyVsBlueCollarDelta !== null);
  const largestBigMoneyVsBlueCollarDifference = withBcDelta.length
    ? withBcDelta.reduce((best, r) => (Math.abs(r.bigMoneyVsBlueCollarDelta!) > Math.abs(best.bigMoneyVsBlueCollarDelta!) ? r : best))
    : null;

  return {
    players: rows.length,
    eligiblePlayers: eligibleRows.length,
    blueCollarCoverage,
    nativeCoverage,
    aiCoverage,
    nativeEligibleCoverage,
    aiEligibleCoverage,
    averageNativeProjection,
    averageAiAdjustment,
    largestAiUpgrade: largestAiUpgrade && largestAiUpgrade.aiVsNativeDelta! > 0 ? largestAiUpgrade : null,
    largestAiDowngrade: largestAiDowngrade && largestAiDowngrade.aiVsNativeDelta! < 0 ? largestAiDowngrade : null,
    largestBigMoneyVsBlueCollarDifference,
  };
}
