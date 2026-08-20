import path from "node:path";

import { getAiProjectionByPlayerId } from "../aiProjections";
import { DK_CLASSIC_SALARY_CAP } from "../dkRosterRules";
import { buildDkSlateVegasCoverage } from "../dkVegasCoverage";
import { safeReadJson } from "../discovery";
import { getProjectionComparisonByPlayerId, loadLatestBaselineSnapshot } from "../externalProjections";
import { getFantasyProsProjectionByPlayerId } from "../fantasyProsProjections";
import { loadLatestEnvironmentReport } from "../gameEnvironment";
import { getNativeProjectionByPlayerId } from "../nativeProjections";
import { fingerprintChanged, ownershipFingerprint, poolFingerprint, providerSlateFingerprint } from "../orchestrator/artifacts";
import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import type { ProviderSource } from "../orchestrator/types";
import type { DKPlayerPool, OwnershipSnapshot } from "../types";
import { parseLastJsonLine } from "./jsonLine";
import type { OptimizerPoolResult, PoolPlayerRow, SlateListResult, SlateOption } from "./types";

const PROVIDER_SOURCE_VALUES = new Set<ProviderSource>(["explicit", "real_dk_csv", "csv_import_pool", "mock_explicit", "unconfigured"]);
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

export async function listSlates(date: string): Promise<SlateListResult> {
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

  const slates: SlateOption[] = (Array.isArray(doc.slates) ? (doc.slates as Record<string, unknown>[]) : []).map((s) => ({
    slateId: String(s.slate_id),
    slateName: (s.slate_name as string | null) ?? null,
    gameCount: (s.game_count as number | null) ?? null,
    startTime: (s.start_time as string | null) ?? null,
    gameIds: Array.isArray(s.game_ids) ? (s.game_ids as string[]) : [],
    playerCount: (s.player_count as number | null) ?? null,
  }));

  return {
    status: (doc.status as SlateListResult["status"]) ?? "unavailable",
    reason: (doc.reason as string | null) ?? null,
    providerName: (doc.provider_name as string | null) ?? null,
    providerType: doc.provider_type === "mock" || doc.provider_type === "real" ? (doc.provider_type as "mock" | "real") : null,
    isMock: Boolean(doc.is_mock),
    isConnected: Boolean(doc.is_connected),
    source: asProviderSource(doc.source),
    slates,
    slatesAvailable: typeof doc.slates_available === "number" ? (doc.slates_available as number) : slates.length,
  };
}

function matchReportPathFor(poolPath: string): string {
  return path.join(path.dirname(poolPath), path.basename(poolPath).replace("dk_player_pool_", "dk_match_report_"));
}

function readPoolResult(entry: CachedPool): OptimizerPoolResult {
  const pool = safeReadJson<DKPlayerPool>(entry.poolPath);
  const matchReport = safeReadJson<Record<string, unknown>>(matchReportPathFor(entry.poolPath));
  const ownership = entry.ownershipPath ? safeReadJson<OwnershipSnapshot>(entry.ownershipPath) : null;

  const ownershipByDkId = new Map<string, OwnershipSnapshot["players"][number]>();
  const ownershipByMlbId = new Map<string, OwnershipSnapshot["players"][number]>();
  for (const p of ownership?.players ?? []) {
    ownershipByDkId.set(p.dk_player_id, p);
    if (p.mlb_player_id) ownershipByMlbId.set(p.mlb_player_id, p);
  }

  const comparisonByPlayerId = getProjectionComparisonByPlayerId(entry.date);
  const aiByPlayerId = getAiProjectionByPlayerId(entry.date);
  const nativeByPlayerId = getNativeProjectionByPlayerId(entry.date);
  const fantasyProsByPlayerId = getFantasyProsProjectionByPlayerId(entry.date);
  const vegasCoverage = buildDkSlateVegasCoverage(matchReport, loadLatestEnvironmentReport(entry.date));

  const players: PoolPlayerRow[] = (pool?.players ?? []).map((p) => {
    const own = ownershipByDkId.get(p.dk_player_id) ?? (p.mlb_player_id ? ownershipByMlbId.get(p.mlb_player_id) : undefined);
    const comparison = p.mlb_player_id ? comparisonByPlayerId.get(p.mlb_player_id) : undefined;
    const ai = p.mlb_player_id ? aiByPlayerId.get(p.mlb_player_id) : undefined;
    const native = p.mlb_player_id ? nativeByPlayerId.get(p.mlb_player_id) : undefined;
    const fantasyPros = p.mlb_player_id ? fantasyProsByPlayerId.get(p.mlb_player_id) : undefined;
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
      fantasyProsMatchStatus: fantasyPros?.match_status ?? null,
    };
  });

  // Milestone 30.1: optimizer_eligible (confirmed starter, see
  // dfs/eligibility.py) replaces lineupStatus === "active" here too --
  // this count feeds the optimizer workspace's own player-pool summary,
  // which must match what the optimizer itself will actually select from.
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
    externalProviderName: loadLatestBaselineSnapshot(entry.date)?.provider_name ?? null,
    hasAiProjections: aiByPlayerId.size > 0,
    hasNativeProjections: nativeByPlayerId.size > 0,
    hasFantasyProsProjections: fantasyProsByPlayerId.size > 0,
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

  const providerBefore = providerSlateFingerprint(date);
  const fetchResult = await runPythonScript("scripts/fetch_dfs_slate.py", ["--date", date, "--slate-id", slateId]);
  const providerAfter = providerSlateFingerprint(date);
  if (fetchResult.exitCode !== 0 || !fingerprintChanged(providerBefore, providerAfter) || !providerAfter.path) {
    throw new Error(`Failed to fetch DFS slate ${slateId}: ${tail(fetchResult.stdout + fetchResult.stderr, 1000)}`);
  }
  const providerDoc = safeReadJson<Record<string, unknown>>(providerAfter.path);
  if (providerDoc?.status !== "ready") {
    throw new Error(`Provider slate ${slateId} is not ready (status: ${providerDoc?.status}). ${providerDoc?.reason ?? ""}`);
  }

  const poolBefore = poolFingerprint(date);
  const poolResult = await runPythonScript("scripts/build_dfs_pool_from_provider.py", [
    "--date",
    date,
    "--provider-slate",
    providerAfter.path,
  ]);
  const poolAfter = poolFingerprint(date);
  if (poolResult.exitCode !== 0 || !fingerprintChanged(poolBefore, poolAfter) || !poolAfter.path) {
    throw new Error(`Failed to build player pool for slate ${slateId}: ${tail(poolResult.stdout + poolResult.stderr, 1000)}`);
  }

  // Ownership is best-effort: if there are zero active players yet (e.g.
  // today's Pitcher/Batter Agent runs haven't happened), the projection
  // script still runs cleanly and just produces an (empty) snapshot; if
  // anything else goes wrong, browsing/building continues without
  // ownership rather than failing slate selection entirely.
  let ownershipPath: string | null = null;
  const ownBefore = ownershipFingerprint(date, slateId);
  const ownResult = await runPythonScript("scripts/project_dk_ownership.py", [
    "--date",
    date,
    "--pool",
    poolAfter.path,
    "--slate-id",
    slateId,
  ]);
  const ownAfter = ownershipFingerprint(date, slateId);
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
