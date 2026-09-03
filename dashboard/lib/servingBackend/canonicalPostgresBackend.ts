import { getExecutor } from "../db/executor";
import { getCanonicalOwnershipForSlate, type CanonicalOwnershipRow } from "../db/canonicalOwnership";
import { resolveMlbPlayerIds } from "../db/canonicalPlayerIdentity";
import { getCanonicalProjectionsForSlate, type CanonicalProjectionRow } from "../db/canonicalProjections";
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
// MLB FINISH MODE Phase B/D: `projection`/`ceiling`/`ownership`/`leverage`
// (and their native* mirrors) now come from REAL, persisted Big Money
// Native / ownership computations (lib/db/canonicalProjections.ts,
// lib/db/canonicalOwnership.ts) -- both bridges reuse the real,
// unmodified Python models exactly like eligibility already does, keyed
// by provider_player_id (DK id) so a player is never excluded here just
// because their historical identity hasn't resolved. AI/FantasyPros/
// BlueCollar/ML remain intentionally absent (rule #2: never an automatic
// customer fallback source) -- their fields stay honestly null/false,
// never fabricated.

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

// T3 Step 7: last_validated_at advances on a real, successful re-check
// of the source (including a semantic no-op re-promotion), so an
// actively-healthy slate whose OWN content happens to be unchanged for a
// while is never treated as if nobody had looked at it since promoted_at
// last moved -- see migrations/0014_canonical_slate_last_validated.sql
// and canonicalPromotion.ts's own docstring for exactly which write
// paths advance it. Falls back through the same chain as before for any
// row from before this column existed.
function mostRecentTimestamp(row: CanonicalSlateRow): string | null {
  return row.last_validated_at ?? row.promoted_at ?? row.last_success_at ?? row.fetched_at;
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

// MLB FINISH MODE Phase B/D -- `projection`/`ceiling` below (and the
// mirrored `nativeProjection`/`nativeCeiling`/`nativeFloor` fields) come
// from a REAL, persisted Big Money Native computation (canonicalProjections.ts)
// keyed by provider_player_id (DK id) -- Big Money Native IS this
// codebase's public/default projection source (rule #1), so `projection`
// is populated from it directly rather than staying a separate
// "Independent" baseline concept canonical never had. A player with no
// persisted row here (unresolved identity, or genuinely outside the
// Native engine's coverage) still gets `null`, never a fabricated value
// -- the exact same honest-absence contract every other field on this
// row already uses.
function poolPlayerRowFromCanonical(
  row: CanonicalSlatePlayerRow, mlbPlayerId: string | null,
  projectionRow: CanonicalProjectionRow | undefined, ownershipRow: CanonicalOwnershipRow | undefined,
): PoolPlayerRow {
  const positions = parseJsonArray(row.position_eligibility_json);
  const projection = projectionRow?.projection ?? null;
  const ceiling = projectionRow?.ceiling ?? null;
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
    projection,
    ceiling,
    value: projection !== null && row.salary > 0 ? Math.round((projection / (row.salary / 1000)) * 100) / 100 : null,
    ownership: ownershipRow?.projected_ownership ?? null,
    leverage: ownershipRow?.leverage_score ?? null,
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
    // PROBABLE FIX: real, evidence-based probable-starter fields (see
    // dfs/eligibility.py's own docstring for the full CONFIRMED/PROBABLE
    // mapping) -- null for every status where they don't apply, never
    // fabricated for a player with no real evidence.
    lineupConfirmation: row.lineup_confirmation,
    probableConfidence: row.probable_confidence,
    probableReason: row.probable_reason,
    projectedBattingOrder: row.projected_batting_order,
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
    // `projection`/`ceiling` above ARE the Native values (rule #1: Native
    // is the default projection source, not a separate comparison
    // column, under canonical serving) -- these native* fields mirror
    // them so the UI's existing "Show comparison columns" / BM Native
    // column continues to work unchanged, and nativeDelta is honestly 0
    // rather than fabricated since there is no separate baseline to
    // diff against here.
    nativeProjection: projection,
    nativeCeiling: ceiling,
    nativeFloor: projectionRow?.floor ?? null,
    nativeDelta: projection !== null ? 0 : null,
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
  const [mlbPlayerIdByInternalPlayerId, projectionsByDkId, ownershipByDkId] = await Promise.all([
    resolveMlbPlayerIds(resolvedInternalPlayerIds),
    getCanonicalProjectionsForSlate(slateRow.internal_slate_id),
    getCanonicalOwnershipForSlate(slateRow.internal_slate_id),
  ]);

  const players = playerRows.map((row) =>
    poolPlayerRowFromCanonical(
      row, row.internal_player_id ? (mlbPlayerIdByInternalPlayerId.get(row.internal_player_id) ?? null) : null,
      projectionsByDkId.get(row.provider_player_id), ownershipByDkId.get(row.provider_player_id),
    ),
  );

  const activePlayers = players.filter((p) => p.optimizerEligible);
  const confirmedGameIds = new Set(activePlayers.filter((p) => p.playerType === "hitter" && p.gameId).map((p) => p.gameId as string));
  // T3 Step 3/9 -- this WAS hardcoded to 0 with a comment claiming "no
  // lineup-confirmation concept exists under canonical serving," which
  // stopped being true once M6 added real dfs/eligibility.py-derived
  // eligibilityStatus. Mirrors poolCache.ts's own identical formula.
  const unconfirmedGameIds = new Set(
    players.filter((p) => p.playerType === "hitter" && p.eligibilityStatus === "LINEUP_UNCONFIRMED" && p.gameId).map((p) => p.gameId as string),
  );
  const unmatchedCount = playerRows.filter((p) => p.identity_status === "UNRESOLVED").length;
  const lastUpdatedAt = mostRecentTimestamp(slateRow) ?? new Date().toISOString();
  const age = ageMs(lastUpdatedAt);
  // T3 Step 3/9 -- SLATE freshness (lastUpdatedAt/age above, from
  // last_validated_at/promoted_at) and RESEARCH/LINEUP freshness are
  // deliberately kept as two separate signals here (T3's own explicit
  // instruction not to conflate them) -- the most recent real eligibility
  // computation across this slate's players, or null if it has never
  // been computed at all (honest, never fabricated as "now").
  const eligibilityTimestamps = playerRows.map((p) => p.eligibility_computed_at).filter((t): t is string => t !== null);
  const eligibilityComputedAt = eligibilityTimestamps.length > 0 ? eligibilityTimestamps.sort().at(-1)! : null;

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
    unconfirmedLineupGames: unconfirmedGameIds.size,
    unmatchedCount,
    slateGames: slateRow.game_count ?? 0,
    // Structural-only: real players exist at all. NOT the legacy
    // pipeline's rigorous per-position confirmed-starter feasibility
    // check (dfs/roster_feasibility.py), which is meaningless without
    // lineup-confirmation data -- see this module's scope-gap docstring.
    rosterFeasibilityPass: players.length > 0,
    salaryCap: slateRow.salary_cap ?? DK_CLASSIC_SALARY_CAP,
    hasOwnership: ownershipByDkId.size > 0,
    hasExternalProjections: false,
    externalProviderName: null,
    hasAiProjections: false,
    hasNativeProjections: projectionsByDkId.size > 0,
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
    eligibilityComputedAt,
  };
}

export const CanonicalPostgresServingBackend: SlateServingBackend = {
  kind: "CANONICAL_POSTGRES",
  listSlates: (date: string, sport?: string) => canonicalListSlates(date, sport),
  getSlatePool: (date: string, providerSlateId: string, sport?: string) => canonicalGetSlatePool(date, providerSlateId, sport),
};
