import { getExecutor } from "../db/executor";
import { resolveMlbPlayerIds } from "../db/canonicalPlayerIdentity";
import type { CanonicalSlatePlayerRow, CanonicalSlateRow } from "../db/types";
import { computeBlueCollarCoverage } from "../blueCollarProjections";
import { DK_CLASSIC_SALARY_CAP } from "../dkRosterRules";
import { buildDkSlateVegasCoverage } from "../dkVegasCoverage";
import type { ProviderSource, SlateOption } from "../orchestrator/types";
import type { OptimizerPoolResult, PoolPlayerRow, ProviderDataStatus, SlateListResult } from "../optimizerWorkspace/types";
import type { SlateServingBackend } from "./types";

// M5B -- canonical Postgres read model. Reads ONLY already-promoted,
// structurally-VALID canonical CURRENT state (slates/slate_players/
// players/player_external_ids) -- never a live DraftKings call, never
// mock/CSV data (M5 rule #2/#3). Unresolved identity is servable, never
// blocking (mlbPlayerId is simply null for an unresolved player -- see
// resolveMlbPlayerIds in ../db/canonicalPlayerIdentity.ts).
//
// M6A/M6H: eligibilityStatus/optimizerEligible/gameId/battingOrder now
// come from REAL dfs/eligibility.py computation results, persisted on
// slate_players by scripts/compute_canonical_eligibility.py via
// lib/db/canonicalEligibility.ts (see that module's own docstring for
// the full Python<->Postgres bridge). A player whose eligibility has
// never been computed yet reports eligibilityStatus=null,
// optimizerEligible=false -- an honest "not yet computed" state, NEVER
// an assumed-eligible default (M6 rule #9: do not mark every DK
// draftable optimizerEligible=true).
//
// REMAINING HONEST SCOPE GAP, disclosed here and in the M6 final report:
// canonical Postgres still has NO projection/ownership/AI/ML/BlueCollar
// enrichment (those are all separate file-based artifacts keyed by
// mlbPlayerId, entirely independent of which salary/roster source is
// used, and are simply absent here -- never fabricated, per M5/M6 rule
// #4). A canonical-served pool can therefore have real, non-fabricated
// eligibility now, but still cannot run a real projection-objective
// optimizer build (see dashboard/lib/optimizerWorkspace/buildRunner.ts's
// own M6I/M6M docstring) -- this remains a documented blocker for the
// M5M/M6 cutover gate.

const DEFAULT_SPORT = "MLB";
const DEFAULT_SITE = "draftkings";

// Same reuse-window ceilings poolCache.ts uses for the legacy artifact,
// applied here to a canonical slate row's own promoted_at/last_success_at
// -- keeps FRESH/STALE/ABSENT behavior consistent across both backends
// (M5F: reuse existing concepts, never invent a second freshness model).
const FRESHNESS_MS = 15 * 60 * 1000;
const STALE_MAX_MS = 2 * 60 * 60 * 1000;

const PITCHER_DK_POSITIONS = new Set(["P", "SP", "RP"]);

function inferPlayerType(positions: string[]): "pitcher" | "hitter" {
  return positions.some((p) => PITCHER_DK_POSITIONS.has(p)) ? "pitcher" : "hitter";
}

function parseJsonArray(json: string | null): string[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function mostRecentTimestamp(row: CanonicalSlateRow): string | null {
  return row.promoted_at ?? row.last_success_at ?? row.fetched_at;
}

function ageMs(timestamp: string | null): number | null {
  if (!timestamp) return null;
  const parsed = Date.parse(timestamp);
  return Number.isNaN(parsed) ? null : Date.now() - parsed;
}

function freshnessFor(row: CanonicalSlateRow): ProviderDataStatus | "expired" | null {
  const age = ageMs(mostRecentTimestamp(row));
  if (age === null) return null;
  if (age <= FRESHNESS_MS) return "fresh";
  if (age <= STALE_MAX_MS) return "stale";
  return "expired";
}

function mapSourceProvenance(sourceProvenance: string): ProviderSource | null {
  return sourceProvenance === "DRAFTKINGS_UNOFFICIAL_LIVE" ? "draftkings_unofficial_live" : null;
}

function slateOptionFromRow(row: CanonicalSlateRow): SlateOption {
  return {
    slateId: row.provider_slate_id,
    slateName: row.slate_name,
    gameCount: row.game_count,
    startTime: row.first_game_start_utc,
    gameIds: parseJsonArray(row.game_ids_json),
    playerCount: row.player_count,
  };
}

export async function canonicalListSlates(date: string, sport: string = DEFAULT_SPORT): Promise<SlateListResult> {
  const db = getExecutor();
  const rows = await db.all<CanonicalSlateRow>(
    "SELECT * FROM slates WHERE sport = ? AND slate_date = ? AND validation_state = 'VALID' ORDER BY provider_slate_id",
    [sport, date],
  );

  if (rows.length === 0) {
    return {
      status: "no_slate",
      reason: `No promoted canonical ${sport} slate found for ${date}.`,
      providerName: null,
      providerType: null,
      isMock: false,
      isConnected: true,
      source: null,
      slates: [],
      slatesAvailable: 0,
      dataStatus: null,
      artifactAgeSeconds: null,
      lastUpdatedAt: null,
    };
  }

  // Conservative: the OLDEST promotion among the matched slates decides
  // the list's overall freshness disclosure -- a healthy sibling slate
  // must never hide a stale one (M5F: stale data is served WITH
  // disclosure, never silently).
  let worst: ProviderDataStatus | "expired" | null = "fresh";
  let oldestTimestamp: string | null = null;
  let oldestAge = -Infinity;
  for (const row of rows) {
    const status = freshnessFor(row);
    if (status === "expired" || (status === "stale" && worst !== "expired")) worst = status;
    else if (status === null && worst === "fresh") worst = null;
    const age = ageMs(mostRecentTimestamp(row));
    if (age !== null && age > oldestAge) {
      oldestAge = age;
      oldestTimestamp = mostRecentTimestamp(row);
    }
  }

  if (worst === "expired") {
    return {
      status: "stale_expired",
      reason: "Canonical Postgres slate data was last promoted too long ago to serve safely -- the automatic worker appears to be delayed.",
      providerName: rows[0].provider,
      providerType: "real",
      isMock: false,
      isConnected: true,
      source: mapSourceProvenance(rows[0].source_provenance),
      slates: [],
      slatesAvailable: 0,
      dataStatus: null,
      artifactAgeSeconds: oldestAge >= 0 ? Math.round(oldestAge / 1000) : null,
      lastUpdatedAt: oldestTimestamp,
    };
  }

  return {
    status: "ready",
    reason: null,
    providerName: rows[0].provider,
    providerType: "real",
    isMock: false,
    isConnected: true,
    source: mapSourceProvenance(rows[0].source_provenance),
    slates: rows.map(slateOptionFromRow),
    slatesAvailable: rows.length,
    dataStatus: worst === null ? "fresh" : worst,
    artifactAgeSeconds: oldestAge >= 0 ? Math.round(oldestAge / 1000) : null,
    lastUpdatedAt: oldestTimestamp,
  };
}

function poolPlayerRowFromCanonical(row: CanonicalSlatePlayerRow, mlbPlayerId: string | null): PoolPlayerRow {
  const positions = parseJsonArray(row.position_eligibility_json);
  return {
    dkPlayerId: row.provider_player_id,
    mlbPlayerId,
    name: row.name,
    team: row.team,
    opponent: row.opponent,
    gameId: row.game_id,
    playerType: inferPlayerType(positions),
    positions,
    battingOrder: row.batting_order,
    salary: row.salary,
    projection: null,
    ceiling: null,
    value: null,
    ownership: null,
    leverage: null,
    risk: null,
    confidence: null,
    // M6A: real dfs/eligibility.py status when computed
    // (STARTING_PITCHER/STARTING_HITTER/LINEUP_UNCONFIRMED/BENCH/
    // RELIEF_PITCHER/SCRATCHED/UNMATCHED/AMBIGUOUS); "PENDING_ELIGIBILITY"
    // -- a value distinct from every real eligibility.py status -- when
    // eligibility_computed_at is still null (never computed yet for this
    // player). Never optimizerEligible=true merely because a row exists.
    lineupStatus: row.eligibility_status ?? "PENDING_ELIGIBILITY",
    matchStatus: row.identity_status === "RESOLVED" ? "matched" : row.identity_status === "REVIEW_REQUIRED" ? "ambiguous" : "unmatched",
    eligibilityStatus: row.eligibility_status ?? "PENDING_ELIGIBILITY",
    optimizerEligible: row.optimizer_eligible === 1,
    externalProjection: null,
    adjustedProjection: null,
    adjustmentDelta: null,
    adjustmentPercent: null,
    adjustmentReasons: [],
    aiProjection: null,
    aiCeiling: null,
    aiFloor: null,
    aiDelta: null,
    aiConfidence: null,
    aiRisk: null,
    aiGrade: null,
    aiValueScore: null,
    aiSignals: [],
    aiReasons: [],
    aiSummary: null,
    nativeProjection: null,
    nativeCeiling: null,
    nativeFloor: null,
    nativeDelta: null,
    nativeConfidence: null,
    nativeReasons: [],
    nativeExpectedPa: null,
    nativeExpectedInnings: null,
    nativeHitterComponents: null,
    nativePitcherComponents: null,
    fantasyProsProjection: null,
    fantasyProsMatchStatus: null,
    mlProjection: null,
    mlDataQualityScore: null,
    mlProjectionStatus: null,
    mlFeatureTimestamp: null,
    blueCollarProjection: null,
    blueCollarRawProjection: null,
    blueCollarMatchStatus: null,
  };
}

export async function canonicalGetSlatePool(
  date: string, providerSlateId: string, sport: string = DEFAULT_SPORT, site: string = DEFAULT_SITE,
): Promise<OptimizerPoolResult> {
  const db = getExecutor();
  const slateRow = await db.get<CanonicalSlateRow>(
    "SELECT * FROM slates WHERE sport = ? AND site = ? AND provider_slate_id = ? AND slate_date = ? AND validation_state = 'VALID'",
    [sport, site, providerSlateId, date],
  );
  if (!slateRow) {
    throw new Error(`Canonical slate ${providerSlateId} not found for ${date} (absent, not yet promoted, or not a VALID slate).`);
  }

  const freshness = freshnessFor(slateRow);
  if (freshness === "expired") {
    const age = ageMs(mostRecentTimestamp(slateRow));
    throw new Error(
      `Canonical Postgres data for slate ${providerSlateId} was last promoted ` +
        `${age !== null ? `${Math.round(age / 60000)} minutes` : "an unknown amount of time"} ago, which is too old to use safely. ` +
        "The automatic worker appears to be delayed -- please check back shortly.",
    );
  }

  const playerRows = await db.all<CanonicalSlatePlayerRow>(
    "SELECT * FROM slate_players WHERE internal_slate_id = ? ORDER BY provider_player_id",
    [slateRow.internal_slate_id],
  );
  const resolvedInternalPlayerIds = playerRows.map((p) => p.internal_player_id).filter((id): id is string => id !== null);
  const mlbPlayerIdByInternalPlayerId = await resolveMlbPlayerIds(resolvedInternalPlayerIds);

  const players = playerRows.map((row) =>
    poolPlayerRowFromCanonical(row, row.internal_player_id ? (mlbPlayerIdByInternalPlayerId.get(row.internal_player_id) ?? null) : null),
  );

  const activePlayers = players.filter((p) => p.optimizerEligible);
  const confirmedGameIds = new Set(activePlayers.filter((p) => p.playerType === "hitter" && p.gameId).map((p) => p.gameId as string));
  const unmatchedCount = playerRows.filter((p) => p.identity_status === "UNRESOLVED").length;
  const lastUpdatedAt = mostRecentTimestamp(slateRow) ?? new Date().toISOString();
  const age = ageMs(lastUpdatedAt);

  return {
    date,
    slateId: providerSlateId,
    slateName: slateRow.slate_name,
    providerName: slateRow.provider,
    isMock: false,
    providerSource: mapSourceProvenance(slateRow.source_provenance),
    generatedAt: lastUpdatedAt,
    players,
    activePlayers: activePlayers.length,
    pitcherCount: activePlayers.filter((p) => p.playerType === "pitcher").length,
    hitterCount: activePlayers.filter((p) => p.playerType === "hitter").length,
    confirmedLineupGames: confirmedGameIds.size,
    // No lineup-confirmation concept exists under canonical serving (see
    // this module's scope-gap docstring) -- every real player is either
    // present (active) or absent, never "unconfirmed."
    unconfirmedLineupGames: 0,
    unmatchedCount,
    slateGames: slateRow.game_count ?? 0,
    // Structural-only: real players exist at all. NOT the legacy
    // pipeline's rigorous per-position confirmed-starter feasibility
    // check (dfs/roster_feasibility.py), which is meaningless without
    // lineup-confirmation data -- see this module's scope-gap docstring.
    rosterFeasibilityPass: players.length > 0,
    salaryCap: slateRow.salary_cap ?? DK_CLASSIC_SALARY_CAP,
    hasOwnership: false,
    hasExternalProjections: false,
    externalProviderName: null,
    hasAiProjections: false,
    hasNativeProjections: false,
    hasFantasyProsProjections: false,
    hasMlProjections: false,
    hasBlueCollarProjections: false,
    blueCollarSlateName: null,
    blueCollarSlateMatchStatus: null,
    blueCollarUpdated: null,
    blueCollarCoverage: computeBlueCollarCoverage(null, new Set()),
    vegasCoverage: buildDkSlateVegasCoverage(null, null),
    dataStatus: freshness === "stale" ? "stale" : "fresh",
    artifactAgeSeconds: age !== null ? Math.round(age / 1000) : 0,
    lastUpdatedAt,
  };
}

export const CanonicalPostgresServingBackend: SlateServingBackend = {
  kind: "CANONICAL_POSTGRES",
  listSlates: (date: string, sport?: string) => canonicalListSlates(date, sport),
  getSlatePool: (date: string, providerSlateId: string, sport?: string) => canonicalGetSlatePool(date, providerSlateId, sport),
};
