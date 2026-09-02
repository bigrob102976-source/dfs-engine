import { CanonicalPostgresServingBackend } from "./canonicalPostgresBackend";
import { LegacyR2ServingBackend } from "./legacyR2Backend";
import type { OptimizerPoolResult } from "../optimizerWorkspace/types";

// M5D/M5E -- ADMIN-only shadow comparison between the two serving
// backends for one real slate. Compares only the CORE identity/salary/
// roster fields canonical Postgres actually tracks (DraftGroup/slate
// date, game count, player count, player IDs, salaries, positions,
// teams, opponents, provenance) -- see canonicalPostgresBackend.ts's own
// scope-gap docstring for why projection/ownership/lineup-status fields
// are intentionally NOT compared here (canonical Postgres carries none
// of that data by design in this milestone). "Draftable IDs" (also
// listed in M5D) are likewise out of scope for this comparison: the
// shared OptimizerPoolResult/PoolPlayerRow domain shape both backends
// return does not carry them at all (they're an identity-internal
// field, stripped before reaching this customer-facing shape on the
// legacy side too) -- comparing them would require reading raw
// provider artifacts directly, deferred as a known limitation.
//
// Never exposes a secret: both backends' results are already
// customer-facing-safe domain objects (no DB connection string,
// storage credential, or API key ever passes through either).

export interface PlayerFieldComparison {
  dkPlayerId: string;
  legacySalary: number;
  canonicalSalary: number;
  legacyTeam: string;
  canonicalTeam: string;
  legacyOpponent: string | null;
  canonicalOpponent: string | null;
  legacyPositions: string[];
  canonicalPositions: string[];
}

// M6O -- eligibility parity is a SEPARATE comparison from M5D/M5E's own
// core identity/salary/roster `match`/`differences` (kept unchanged
// above for backward compatibility): legacy's eligibility comes from
// dfs/player_resolver.py's own research-package name+team matching,
// while canonical's comes from the player_identity/ crosswalk bridge
// (canonical_ingestion/identity_bridge.py) -- two INDEPENDENT identity
// systems that both eventually feed the SAME dfs/eligibility.py::
// compute_eligibility(). Some genuine, explainable divergence between
// them is expected and reported honestly here, never silently folded
// into (or hidden from) the core M5 `match` signal above.
export interface EligibilityFieldComparison {
  dkPlayerId: string;
  legacyEligibilityStatus: string | null;
  canonicalEligibilityStatus: string | null;
  legacyOptimizerEligible: boolean;
  canonicalOptimizerEligible: boolean;
  legacyGameId: string | null;
  canonicalGameId: string | null;
  legacyMlbPlayerId: string | null;
  canonicalMlbPlayerId: string | null;
}

export interface SlateComparisonResult {
  date: string;
  slateId: string;
  legacyFound: boolean;
  canonicalFound: boolean;
  legacyError: string | null;
  canonicalError: string | null;
  match: boolean;
  legacy: { slateName: string | null; gameCount: number; playerCount: number; salaryCap: number; providerSource: string | null } | null;
  canonical: { slateName: string | null; gameCount: number; playerCount: number; salaryCap: number; providerSource: string | null } | null;
  differences: {
    slateNameMismatch: boolean;
    gameCountMismatch: boolean;
    playerCountMismatch: boolean;
    salaryCapMismatch: boolean;
    provenanceMismatch: boolean;
    missingInCanonical: string[];
    missingInLegacy: string[];
    salaryMismatches: PlayerFieldComparison[];
    positionMismatches: PlayerFieldComparison[];
    teamMismatches: PlayerFieldComparison[];
    opponentMismatches: PlayerFieldComparison[];
  };
  // M6O -- eligibility parity report, computed only for players present
  // on BOTH sides (the M5-level missingInCanonical/missingInLegacy sets
  // above already report identity gaps at the roster level).
  eligibility: {
    playersCompared: number;
    exactMatches: number;
    statusMismatches: EligibilityFieldComparison[];
    optimizerEligibleMismatches: EligibilityFieldComparison[];
    gameIdMismatches: EligibilityFieldComparison[];
    identityGaps: EligibilityFieldComparison[]; // one side resolved an mlbPlayerId, the other didn't
  };
}

function summarize(pool: OptimizerPoolResult) {
  return { slateName: pool.slateName, gameCount: pool.slateGames, playerCount: pool.players.length, salaryCap: pool.salaryCap, providerSource: pool.providerSource };
}

function sortedPositions(positions: string[]): string {
  return [...positions].sort().join(",");
}

export async function compareServingBackends(date: string, providerSlateId: string): Promise<SlateComparisonResult> {
  const [legacySettled, canonicalSettled] = await Promise.allSettled([
    LegacyR2ServingBackend.getSlatePool(date, providerSlateId),
    CanonicalPostgresServingBackend.getSlatePool(date, providerSlateId),
  ]);

  const legacyPool = legacySettled.status === "fulfilled" ? legacySettled.value : null;
  const canonicalPool = canonicalSettled.status === "fulfilled" ? canonicalSettled.value : null;
  const legacyError = legacySettled.status === "rejected" ? String(legacySettled.reason instanceof Error ? legacySettled.reason.message : legacySettled.reason) : null;
  const canonicalError = canonicalSettled.status === "rejected" ? String(canonicalSettled.reason instanceof Error ? canonicalSettled.reason.message : canonicalSettled.reason) : null;

  const result: SlateComparisonResult = {
    date, slateId: providerSlateId,
    legacyFound: legacyPool !== null, canonicalFound: canonicalPool !== null,
    legacyError, canonicalError,
    match: false,
    legacy: legacyPool ? summarize(legacyPool) : null,
    canonical: canonicalPool ? summarize(canonicalPool) : null,
    differences: {
      slateNameMismatch: false, gameCountMismatch: false, playerCountMismatch: false, salaryCapMismatch: false, provenanceMismatch: false,
      missingInCanonical: [], missingInLegacy: [], salaryMismatches: [], positionMismatches: [], teamMismatches: [], opponentMismatches: [],
    },
    eligibility: { playersCompared: 0, exactMatches: 0, statusMismatches: [], optimizerEligibleMismatches: [], gameIdMismatches: [], identityGaps: [] },
  };

  if (!legacyPool || !canonicalPool) return result;

  result.differences.slateNameMismatch = legacyPool.slateName !== canonicalPool.slateName;
  result.differences.gameCountMismatch = legacyPool.slateGames !== canonicalPool.slateGames;
  result.differences.playerCountMismatch = legacyPool.players.length !== canonicalPool.players.length;
  result.differences.salaryCapMismatch = legacyPool.salaryCap !== canonicalPool.salaryCap;
  result.differences.provenanceMismatch = legacyPool.providerSource !== canonicalPool.providerSource;

  const legacyByDkId = new Map(legacyPool.players.map((p) => [p.dkPlayerId, p]));
  const canonicalByDkId = new Map(canonicalPool.players.map((p) => [p.dkPlayerId, p]));

  for (const dkPlayerId of legacyByDkId.keys()) {
    if (!canonicalByDkId.has(dkPlayerId)) result.differences.missingInCanonical.push(dkPlayerId);
  }
  for (const dkPlayerId of canonicalByDkId.keys()) {
    if (!legacyByDkId.has(dkPlayerId)) result.differences.missingInLegacy.push(dkPlayerId);
  }

  for (const [dkPlayerId, legacyPlayer] of legacyByDkId) {
    const canonicalPlayer = canonicalByDkId.get(dkPlayerId);
    if (!canonicalPlayer) continue;
    const field: PlayerFieldComparison = {
      dkPlayerId,
      legacySalary: legacyPlayer.salary, canonicalSalary: canonicalPlayer.salary,
      legacyTeam: legacyPlayer.team, canonicalTeam: canonicalPlayer.team,
      legacyOpponent: legacyPlayer.opponent, canonicalOpponent: canonicalPlayer.opponent,
      legacyPositions: legacyPlayer.positions, canonicalPositions: canonicalPlayer.positions,
    };
    if (legacyPlayer.salary !== canonicalPlayer.salary) result.differences.salaryMismatches.push(field);
    if (sortedPositions(legacyPlayer.positions) !== sortedPositions(canonicalPlayer.positions)) result.differences.positionMismatches.push(field);
    if (legacyPlayer.team !== canonicalPlayer.team) result.differences.teamMismatches.push(field);
    if (legacyPlayer.opponent !== canonicalPlayer.opponent) result.differences.opponentMismatches.push(field);

    // M6O: eligibility parity, for players present on both sides only.
    result.eligibility.playersCompared += 1;
    const eligField: EligibilityFieldComparison = {
      dkPlayerId,
      legacyEligibilityStatus: legacyPlayer.eligibilityStatus, canonicalEligibilityStatus: canonicalPlayer.eligibilityStatus,
      legacyOptimizerEligible: legacyPlayer.optimizerEligible, canonicalOptimizerEligible: canonicalPlayer.optimizerEligible,
      legacyGameId: legacyPlayer.gameId, canonicalGameId: canonicalPlayer.gameId,
      legacyMlbPlayerId: legacyPlayer.mlbPlayerId, canonicalMlbPlayerId: canonicalPlayer.mlbPlayerId,
    };
    let eligExact = true;
    if (legacyPlayer.eligibilityStatus !== canonicalPlayer.eligibilityStatus) {
      result.eligibility.statusMismatches.push(eligField);
      eligExact = false;
    }
    if (legacyPlayer.optimizerEligible !== canonicalPlayer.optimizerEligible) {
      result.eligibility.optimizerEligibleMismatches.push(eligField);
      eligExact = false;
    }
    if (legacyPlayer.gameId !== canonicalPlayer.gameId) {
      result.eligibility.gameIdMismatches.push(eligField);
      eligExact = false;
    }
    if ((legacyPlayer.mlbPlayerId === null) !== (canonicalPlayer.mlbPlayerId === null)) {
      result.eligibility.identityGaps.push(eligField);
      eligExact = false;
    }
    if (eligExact) result.eligibility.exactMatches += 1;
  }

  const d = result.differences;
  result.match =
    !d.slateNameMismatch && !d.gameCountMismatch && !d.playerCountMismatch && !d.salaryCapMismatch && !d.provenanceMismatch &&
    d.missingInCanonical.length === 0 && d.missingInLegacy.length === 0 &&
    d.salaryMismatches.length === 0 && d.positionMismatches.length === 0 && d.teamMismatches.length === 0 && d.opponentMismatches.length === 0;

  return result;
}

export interface ParityReport {
  date: string;
  slatesCompared: number;
  exactMatches: number;
  mismatches: number;
  missingPlayers: number; // sum of missingInCanonical across all slates
  extraPlayers: number; // sum of missingInLegacy across all slates
  salaryMismatches: number;
  // M6O: real eligibility parity aggregates (previously a fixed
  // "not compared" note pre-M6 -- see EligibilityFieldComparison's own
  // docstring for why some divergence between the two INDEPENDENT
  // identity systems feeding eligibility is expected and honest, not
  // necessarily a bug).
  eligibilityPlayersCompared: number;
  eligibilityExactMatches: number;
  eligibilityStatusMismatches: number;
  eligibilityOptimizerEligibleMismatches: number;
  eligibilityGameIdMismatches: number;
  eligibilityIdentityGaps: number;
  perSlate: SlateComparisonResult[];
  errors: string[];
}

/** M5E/M6O -- parity across every real, currently-listed Classic slate
 * for `date`. Compared against LEGACY's own slate list (the side with
 * the richer, already-customer-serving history) so a slate canonical
 * hasn't promoted yet shows up as a real, visible mismatch rather than
 * being silently skipped. */
export async function compareAllServingBackendsForDate(date: string): Promise<ParityReport> {
  const legacyList = await LegacyR2ServingBackend.listSlates(date);
  const errors: string[] = [];
  if (legacyList.status !== "ready") errors.push(`Legacy slate list for ${date}: ${legacyList.status} -- ${legacyList.reason ?? "no reason given"}`);

  const perSlate: SlateComparisonResult[] = [];
  for (const slate of legacyList.slates) {
    perSlate.push(await compareServingBackends(date, slate.slateId));
  }

  return {
    date,
    slatesCompared: perSlate.length,
    exactMatches: perSlate.filter((c) => c.match).length,
    mismatches: perSlate.filter((c) => !c.match).length,
    missingPlayers: perSlate.reduce((sum, c) => sum + c.differences.missingInCanonical.length, 0),
    extraPlayers: perSlate.reduce((sum, c) => sum + c.differences.missingInLegacy.length, 0),
    salaryMismatches: perSlate.reduce((sum, c) => sum + c.differences.salaryMismatches.length, 0),
    eligibilityPlayersCompared: perSlate.reduce((sum, c) => sum + c.eligibility.playersCompared, 0),
    eligibilityExactMatches: perSlate.reduce((sum, c) => sum + c.eligibility.exactMatches, 0),
    eligibilityStatusMismatches: perSlate.reduce((sum, c) => sum + c.eligibility.statusMismatches.length, 0),
    eligibilityOptimizerEligibleMismatches: perSlate.reduce((sum, c) => sum + c.eligibility.optimizerEligibleMismatches.length, 0),
    eligibilityGameIdMismatches: perSlate.reduce((sum, c) => sum + c.eligibility.gameIdMismatches.length, 0),
    eligibilityIdentityGaps: perSlate.reduce((sum, c) => sum + c.eligibility.identityGaps.length, 0),
    perSlate,
    errors,
  };
}
