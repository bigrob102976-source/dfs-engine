import path from "node:path";

import { getAiProjectionByPlayerId } from "../aiProjections";
import { DK_CLASSIC_SALARY_CAP } from "../dkRosterRules";
import { buildDkSlateVegasCoverage } from "../dkVegasCoverage";
import { safeReadJson } from "../discovery";
import { getProjectionComparisonByPlayerId, loadLatestBaselineSnapshot } from "../externalProjections";
import { computeBlueCollarCoverage, getBlueCollarProjectionByPlayerId, loadLatestBlueCollarSnapshot } from "../blueCollarProjections";
import { getFantasyProsProjectionByPlayerId } from "../fantasyProsProjections";
import { loadLatestEnvironmentReport } from "../gameEnvironment";
import { getMlProjectionByPlayerId } from "../mlProjections";
import { getNativeProjectionByPlayerId } from "../nativeProjections";
import { fingerprintChanged, ownershipFingerprint, poolFingerprint, providerSlateFingerprint } from "../orchestrator/artifacts";
import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import type { ProviderSource } from "../orchestrator/types";
import type { DKPlayerPool, OwnershipSnapshot } from "../types";
import { parseLastJsonLine } from "./jsonLine";
import type { OptimizerPoolResult, PoolPlayerRow, SlateListResult, SlateOption } from "./types";

const PROVIDER_SOURCE_VALUES = new Set<ProviderSource>([
  "explicit",
  "draftkings_unofficial_live",
  "real_dk_csv",
  "csv_import_pool",
  "mock_explicit",
  "unconfigured",
]);
function asProviderSource(value: unknown): ProviderSource | null {
  return typeof value === "string" && PROVIDER_SOURCE_VALUES.has(value as ProviderSource) ? (value as ProviderSource) : null;
}

interface CachedPool {
  date: string;
  slateId: string;
  slateName: string | null;
  providerName: string | null;
  isMock: boolean;
  source: ProviderSource | null;
  poolPath: string;
  ownershipPath: string | null;
  builtAt: string;
}

// Module-level cache: a slate's pool is built once (fetch -> build pool
// -> project ownership, all via the same immutable-artifact scripts the
// M13 refresh pipeline already uses) and reused for every subsequent
// browse/build against that (date, slateId) within this Node process,
// instead of re-invoking three Python scripts and spamming a fresh
// immutable artifact every time the user re-selects the same slate.
const poolCache = new Map<string, CachedPool>();

function cacheKey(date: string, slateId: string): string {
  return `${date}:${slateId}`;
}

export function __resetPoolCacheForTests(): void {
  poolCache.clear();
}

// How recent an already-fetched provider-slate document has to be to
// reuse instead of calling DraftKings live again. DK contest/salary data
// doesn't change second-to-second, so a short reuse window avoids an
// unnecessary live call (and the live call's own failure, e.g. an
// egress IP restriction) on every cache-cold page view without serving
// meaningfully stale data.
const PROVIDER_SLATE_FRESHNESS_MS = 15 * 60 * 1000;

function providerSlateFreshEnough(doc: Record<string, unknown> | null): boolean {
  if (!doc) return false;
  const generatedAt = typeof doc.generated_at_utc === "string" ? Date.parse(doc.generated_at_utc) : NaN;
  if (Number.isNaN(generatedAt)) return false;
  return Date.now() - generatedAt <= PROVIDER_SLATE_FRESHNESS_MS;
}

/** Builds a SlateListResult from a provider-slate document -- shared by
 * listSlates() (list_dfs_slates.py's own doc shape) and its
 * fresh-artifact-reuse path (fetch_dfs_slate.py's doc shape, which
 * lacks is_connected/slates_available but carries the same discovered
 * `slates` array, since selecting one slate never discards the others). */
function slateListResultFromProviderDoc(doc: Record<string, unknown>): SlateListResult {
  const slates: SlateOption[] = (Array.isArray(doc.slates) ? (doc.slates as Record<string, unknown>[]) : []).map((s) => ({
    slateId: String(s.slate_id),
    slateName: (s.slate_name as string | null) ?? null,
    gameCount: (s.game_count as number | null) ?? null,
    startTime: (s.start_time as string | null) ?? null,
    gameIds: Array.isArray(s.game_ids) ? (s.game_ids as string[]) : [],
    playerCount: (s.player_count as number | null) ?? null,
  }));
  const status = (doc.status as SlateListResult["status"]) ?? "unavailable";
  const providerName = (doc.provider_name as string | null) ?? null;
  return {
    status,
    reason: (doc.reason as string | null) ?? null,
    providerName,
    providerType: doc.provider_type === "mock" || doc.provider_type === "real" ? (doc.provider_type as "mock" | "real") : null,
    isMock: Boolean(doc.is_mock),
    isConnected: typeof doc.is_connected === "boolean" ? doc.is_connected : Boolean(providerName) && status === "ready",
    source: asProviderSource(doc.source),
    slates,
    slatesAvailable: typeof doc.slates_available === "number" ? (doc.slates_available as number) : slates.length,
  };
}

export async function listSlates(date: string): Promise<SlateListResult> {
  // A "ready" or "needs_selection" provider-slate document already
  // carries the full discovered `slates` array (selecting one slate
  // never discards the others) -- reuse it when fresh enough instead of
  // calling DraftKings live again.
  const existing = await providerSlateFingerprint(date);
  const existingDoc = await safeReadJson<Record<string, unknown>>(existing.path);
  if (
    existingDoc &&
    (existingDoc.status === "ready" || existingDoc.status === "needs_selection") &&
    providerSlateFreshEnough(existingDoc)
  ) {
    return slateListResultFromProviderDoc(existingDoc);
  }

  const result = await runPythonScript("scripts/list_dfs_slates.py", ["--date", date]);
  const doc = parseLastJsonLine(result.stdout);

  if (!doc || result.exitCode !== 0) {
    return {
      status: "unavailable",
      reason: `Unexpected slate-listing failure: ${tail(result.stdout + result.stderr, 500)}`,
      providerName: null,
      providerType: null,
      isMock: false,
      isConnected: false,
      source: null,
      slates: [],
      slatesAvailable: 0,
    };
  }

  return slateListResultFromProviderDoc(doc);
}

function matchReportPathFor(poolPath: string): string {
  return path.join(path.dirname(poolPath), path.basename(poolPath).replace("dk_player_pool_", "dk_match_report_"));
}

async function readPoolResult(entry: CachedPool): Promise<OptimizerPoolResult> {
  const [pool, matchReport, ownership] = await Promise.all([
    safeReadJson<DKPlayerPool>(entry.poolPath),
    safeReadJson<Record<string, unknown>>(matchReportPathFor(entry.poolPath)),
    entry.ownershipPath ? safeReadJson<OwnershipSnapshot>(entry.ownershipPath) : Promise.resolve(null),
  ]);

  const ownershipByDkId = new Map<string, OwnershipSnapshot["players"][number]>();
  const ownershipByMlbId = new Map<string, OwnershipSnapshot["players"][number]>();
  for (const p of ownership?.players ?? []) {
    ownershipByDkId.set(p.dk_player_id, p);
    if (p.mlb_player_id) ownershipByMlbId.set(p.mlb_player_id, p);
  }

  const [
    comparisonByPlayerId,
    aiByPlayerId,
    nativeByPlayerId,
    fantasyProsByPlayerId,
    // Milestone 32.2B: Big Money ML -- SHADOW MODE, comparison-only join.
    mlByPlayerId,
    // BlueCollar DFS -- comparison + optional ADMIN-only optimizer source,
    // always slate-scoped (never date-only like FantasyPros above).
    blueCollarByPlayerId,
    blueCollarSnapshot,
    environmentReport,
    externalBaselineSnapshot,
  ] = await Promise.all([
    getProjectionComparisonByPlayerId(entry.date),
    getAiProjectionByPlayerId(entry.date),
    getNativeProjectionByPlayerId(entry.date),
    getFantasyProsProjectionByPlayerId(entry.date),
    getMlProjectionByPlayerId(entry.date),
    getBlueCollarProjectionByPlayerId(entry.date, entry.slateId),
    loadLatestBlueCollarSnapshot(entry.date, entry.slateId),
    loadLatestEnvironmentReport(entry.date),
    loadLatestBaselineSnapshot(entry.date),
  ]);
  const vegasCoverage = buildDkSlateVegasCoverage(matchReport, environmentReport);

  const players: PoolPlayerRow[] = (pool?.players ?? []).map((p) => {
    const own = ownershipByDkId.get(p.dk_player_id) ?? (p.mlb_player_id ? ownershipByMlbId.get(p.mlb_player_id) : undefined);
    const comparison = p.mlb_player_id ? comparisonByPlayerId.get(p.mlb_player_id) : undefined;
    const ai = p.mlb_player_id ? aiByPlayerId.get(p.mlb_player_id) : undefined;
    const native = p.mlb_player_id ? nativeByPlayerId.get(p.mlb_player_id) : undefined;
    const fantasyPros = p.mlb_player_id ? fantasyProsByPlayerId.get(p.mlb_player_id) : undefined;
    const ml = p.mlb_player_id ? mlByPlayerId.get(p.mlb_player_id) : undefined;
    const blueCollar = p.mlb_player_id ? blueCollarByPlayerId.get(p.mlb_player_id) : undefined;
    const mlIsValidPregame = ml?.projection_status === "LIVE_PREGAME" || ml?.projection_status === "PREGAME_FROZEN";
    return {
      dkPlayerId: p.dk_player_id,
      mlbPlayerId: p.mlb_player_id,
      name: p.name,
      team: p.team,
      opponent: p.opponent,
      gameId: p.game_id,
      playerType: p.player_type,
      positions: p.dk_positions,
      battingOrder: p.batting_order,
      salary: p.salary,
      projection: p.projection,
      ceiling: p.ceiling,
      value: p.projection != null && p.salary > 0 ? Math.round((p.projection / (p.salary / 1000)) * 100) / 100 : null,
      ownership: own?.projected_ownership ?? null,
      leverage: own?.leverage_score ?? null,
      risk: p.risk_score,
      confidence: p.confidence,
      lineupStatus: p.lineup_status,
      matchStatus: p.match_status,
      eligibilityStatus: p.eligibility_status ?? null,
      optimizerEligible: p.optimizer_eligible ?? false,
      externalProjection: comparison?.externalProjection ?? null,
      adjustedProjection: comparison?.adjustedProjection ?? null,
      adjustmentDelta: comparison?.adjustmentDelta ?? null,
      adjustmentPercent: comparison?.adjustmentPercent ?? null,
      adjustmentReasons: comparison?.adjustmentReasons ?? [],
      aiProjection: ai?.ai_projection ?? null,
      aiCeiling: ai?.ai_ceiling ?? null,
      aiFloor: ai?.ai_floor ?? null,
      aiDelta: ai?.total_adjustment ?? null,
      aiConfidence: ai?.ai_confidence ?? null,
      aiRisk: ai?.ai_risk ?? null,
      aiGrade: ai?.ai_grade ?? null,
      aiValueScore: ai?.ai_value_score ?? null,
      aiSignals: ai?.signals ?? [],
      aiReasons: ai?.reasons ?? [],
      aiSummary: ai?.ai_summary ?? null,
      nativeProjection: native?.native_projection ?? null,
      nativeCeiling: native?.native_ceiling ?? null,
      nativeFloor: native?.native_floor ?? null,
      nativeDelta: native && p.projection != null ? Math.round((native.native_projection - p.projection) * 100) / 100 : null,
      nativeConfidence: native?.confidence ?? null,
      nativeReasons: native?.reasons ?? [],
      nativeExpectedPa: native?.hitter_opportunity?.expected_pa ?? null,
      nativeExpectedInnings: native?.pitcher_opportunity?.expected_innings ?? null,
      nativeHitterComponents: native?.hitter_components ?? null,
      nativePitcherComponents: native?.pitcher_components ?? null,
      fantasyProsProjection: fantasyPros?.dk_points ?? null,
      mlProjection: mlIsValidPregame ? (ml?.projection ?? null) : null,
      mlDataQualityScore: ml?.data_quality_score ?? null,
      mlProjectionStatus: ml?.projection_status ?? null,
      mlFeatureTimestamp: ml?.feature_timestamp ?? null,
      fantasyProsMatchStatus: fantasyPros?.match_status ?? null,
      blueCollarProjection: blueCollar?.usable_projection ?? null,
      blueCollarRawProjection: blueCollar?.raw_projection ?? null,
      blueCollarMatchStatus: blueCollar?.match_status ?? null,
    };
  });

  // Milestone 30.1: optimizer_eligible (confirmed starter, see
  // dfs/eligibility.py) replaces lineupStatus === "active" here too --
  // this count feeds the optimizer workspace's own player-pool summary,
  // which must match what the optimizer itself will actually select from.
  // M32.7: BlueCollar's own funnel, as separate counts.
  const blueCollarOptimizerIds = new Set(
    players.filter((p) => p.optimizerEligible && p.mlbPlayerId).map((p) => p.mlbPlayerId as string),
  );
  const blueCollarCoverage = computeBlueCollarCoverage(blueCollarSnapshot, blueCollarOptimizerIds);

  const activePlayers = players.filter((p) => p.optimizerEligible);
  const confirmedGameIds = new Set(activePlayers.filter((p) => p.playerType === "hitter" && p.gameId).map((p) => p.gameId as string));
  const unconfirmedGameIds = new Set(
    players.filter((p) => p.playerType === "hitter" && p.eligibilityStatus === "LINEUP_UNCONFIRMED" && p.gameId).map((p) => p.gameId as string),
  );

  return {
    date: entry.date,
    slateId: entry.slateId,
    slateName: entry.slateName,
    providerName: entry.providerName,
    isMock: entry.isMock,
    providerSource: entry.source,
    generatedAt: entry.builtAt,
    players,
    activePlayers: activePlayers.length,
    pitcherCount: activePlayers.filter((p) => p.playerType === "pitcher").length,
    hitterCount: activePlayers.filter((p) => p.playerType === "hitter").length,
    confirmedLineupGames: confirmedGameIds.size,
    unconfirmedLineupGames: unconfirmedGameIds.size,
    unmatchedCount: typeof matchReport?.unmatched_count === "number" ? (matchReport.unmatched_count as number) : 0,
    slateGames: typeof matchReport?.dk_games_total === "number" ? (matchReport.dk_games_total as number) : 0,
    rosterFeasibilityPass: pool?.roster_feasibility_pass ?? false,
    hasExternalProjections: comparisonByPlayerId.size > 0,
    // Milestone 27: the active external baseline's OWN provider_name
    // (e.g. "BlueCollar DFS", "MOCK EXTERNAL PROJECTIONS") -- so the
    // dashboard can label this slot honestly ("BlueCollar" vs "External
    // Other") instead of a bare, ambiguous "External." null whenever no
    // baseline is loaded at all (hasExternalProjections is also false then).
    externalProviderName: externalBaselineSnapshot?.provider_name ?? null,
    hasAiProjections: aiByPlayerId.size > 0,
    hasNativeProjections: nativeByPlayerId.size > 0,
    hasFantasyProsProjections: fantasyProsByPlayerId.size > 0,
    hasMlProjections: mlByPlayerId.size > 0,
    hasBlueCollarProjections: blueCollarByPlayerId.size > 0,
    blueCollarSlateName: blueCollarSnapshot?.bluecollar_slate_name ?? null,
    blueCollarSlateMatchStatus: blueCollarSnapshot?.slate_match_status ?? null,
    blueCollarUpdated: blueCollarSnapshot?.bluecollar_updated ?? null,
    blueCollarCoverage,
    salaryCap: DK_CLASSIC_SALARY_CAP,
    hasOwnership: ownership !== null,
    vegasCoverage,
  };
}

export function getCachedPoolPath(date: string, slateId: string): { poolPath: string; ownershipPath: string | null } | null {
  const entry = poolCache.get(cacheKey(date, slateId));
  return entry ? { poolPath: entry.poolPath, ownershipPath: entry.ownershipPath } : null;
}

/** Selects a slate: fetches it from the provider, builds the unified DFS
 * player pool, and projects ownership against it -- three calls into the
 * exact same immutable-artifact Python scripts the M13 one-click refresh
 * pipeline already uses (scripts/fetch_dfs_slate.py,
 * scripts/build_dfs_pool_from_provider.py, scripts/project_dk_ownership.py).
 * Cached per (date, slateId) so re-selecting the same slate doesn't
 * re-invoke Python or spam new immutable artifacts every time. */
export async function loadPool(date: string, slateId: string, forceRefresh = false): Promise<OptimizerPoolResult> {
  const key = cacheKey(date, slateId);
  const cached = poolCache.get(key);
  if (cached && !forceRefresh) {
    return readPoolResult(cached);
  }

  const providerBefore = await providerSlateFingerprint(date);
  // Reuse an already-fetched, fresh-enough provider-slate document for
  // THIS exact slate (selected_slate_id match -- a document fetched for
  // a different slate on the same date carries no player data for this
  // one) instead of calling DraftKings live again. forceRefresh always
  // bypasses this, same as it always bypassed the pool cache above.
  const existingDoc = !forceRefresh ? await safeReadJson<Record<string, unknown>>(providerBefore.path) : null;
  let providerAfter = providerBefore;
  let providerDoc: Record<string, unknown> | null = null;

  if (existingDoc && existingDoc.status === "ready" && existingDoc.selected_slate_id === slateId && providerSlateFreshEnough(existingDoc)) {
    providerDoc = existingDoc;
  } else {
    const fetchResult = await runPythonScript("scripts/fetch_dfs_slate.py", ["--date", date, "--slate-id", slateId]);
    providerAfter = await providerSlateFingerprint(date);
    if (fetchResult.exitCode !== 0 || !fingerprintChanged(providerBefore, providerAfter) || !providerAfter.path) {
      throw new Error(`Failed to fetch DFS slate ${slateId}: ${tail(fetchResult.stdout + fetchResult.stderr, 1000)}`);
    }
    providerDoc = await safeReadJson<Record<string, unknown>>(providerAfter.path);
  }
  if (providerDoc?.status !== "ready") {
    throw new Error(`Provider slate ${slateId} is not ready (status: ${providerDoc?.status}). ${providerDoc?.reason ?? ""}`);
  }
  if (!providerAfter.path) {
    throw new Error(`Provider slate ${slateId} artifact path is unexpectedly missing.`);
  }

  const poolBefore = await poolFingerprint(date);
  const poolResult = await runPythonScript("scripts/build_dfs_pool_from_provider.py", [
    "--date",
    date,
    "--provider-slate",
    providerAfter.path,
  ]);
  const poolAfter = await poolFingerprint(date);
  if (poolResult.exitCode !== 0 || !fingerprintChanged(poolBefore, poolAfter) || !poolAfter.path) {
    throw new Error(`Failed to build player pool for slate ${slateId}: ${tail(poolResult.stdout + poolResult.stderr, 1000)}`);
  }

  // Ownership is best-effort: if there are zero active players yet (e.g.
  // today's Pitcher/Batter Agent runs haven't happened), the projection
  // script still runs cleanly and just produces an (empty) snapshot; if
  // anything else goes wrong, browsing/building continues without
  // ownership rather than failing slate selection entirely.
  let ownershipPath: string | null = null;
  const ownBefore = await ownershipFingerprint(date, slateId);
  const ownResult = await runPythonScript("scripts/project_dk_ownership.py", [
    "--date",
    date,
    "--pool",
    poolAfter.path,
    "--slate-id",
    slateId,
  ]);
  const ownAfter = await ownershipFingerprint(date, slateId);
  if (ownResult.exitCode === 0 && fingerprintChanged(ownBefore, ownAfter)) {
    ownershipPath = ownAfter.path;
  }

  const providerName = typeof providerDoc?.provider_name === "string" ? (providerDoc.provider_name as string) : null;
  const slates = Array.isArray(providerDoc?.slates) ? (providerDoc!.slates as Record<string, unknown>[]) : [];
  const slateName = (slates.find((s) => s.slate_id === slateId)?.slate_name as string | undefined) ?? null;
  const providerSource = asProviderSource(providerDoc?.source);

  const entry: CachedPool = {
    date,
    slateId,
    slateName,
    providerName,
    isMock: Boolean(providerDoc?.is_mock),
    source: providerSource,
    poolPath: poolAfter.path,
    ownershipPath,
    builtAt: new Date().toISOString(),
  };
  poolCache.set(key, entry);
  return readPoolResult(entry);
}
