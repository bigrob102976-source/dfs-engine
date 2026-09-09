// M32.7: Early Slate Projection Readiness + Automatic Lineup Promotion.
//
// Pure, read-only aggregation over data every page here already loads
// (match report, joined Native/AI rows, ML coverage, BlueCollar
// snapshot, real MLB game status) -- nothing in this file recomputes a
// projection, an eligibility status, or a stack. "Automatic promotion"
// itself needs no new mechanism: dfs/eligibility.py already computes
// eligibility fresh from the CURRENT confirmed-lineup research package
// on every Admin Refresh Data run (see that module's own docstring),
// and Native/AI/ML/ownership/stacks are all recomputed fresh from
// whatever is eligible at that moment -- a newly-confirmed hitter is
// therefore automatically picked up the next time Refresh Data runs,
// with zero special-casing required here. This module exists to make
// that state legible (a "SLATE READINESS" summary, a per-team
// breakdown, and an honest completion-stage label), not to change how
// promotion happens.

import type { BlueCollarSnapshot } from "./blueCollarProjections";
import type { AiRankedPlayer, NativeRankedPlayer, MlCoverageSummary } from "./commandCenter";
import type { ResearchGame } from "./types";
import type { PlayerRow } from "./types";

export interface CoverageCount {
  /** null == genuinely UNKNOWN (the source document this count comes
   * from is absent), which is NOT the same as "zero are covered" and
   * must never be rendered as a number. See buildSlateReadinessSummary. */
  covered: number | null;
  eligible: number;
}

export interface SlateReadinessSummary {
  /** False when no dk_match_report_ document was available. Every field
   * derived from it is null in that case -- callers MUST render those as
   * an explicit unknown, never as 0 and never as a full/confirmed count. */
  matchReportAvailable: boolean;
  dkPlayers: number | null;
  identityResolved: number | null;
  startingPitchers: CoverageCount; // covered = confirmed starters, eligible = every DK pitcher-type row
  lineupsConfirmed: CoverageCount; // covered = teams with a posted lineup, eligible = every team on this slate
  blueCollarUsable: number;
  nativeEligible: CoverageCount;
  aiEligible: CoverageCount;
  mlEligible: CoverageCount;
  optimizerEligible: number | null;
}

function coverage(rows: PlayerRow[], hasValue: (r: PlayerRow) => boolean): CoverageCount {
  const eligible = rows.filter((r) => r.optimizerEligible);
  return { eligible: eligible.length, covered: eligible.filter(hasValue).length };
}

/** `matchReport` is the raw dk_match_report_<ts>.json document (already
 * loaded elsewhere via loadLatestDkMatchReport -- read-only here, never
 * re-derived). `nativeRows`/`aiRows` are the SAME joinNativeProjections/
 * joinAiProjections output every Command Center caller already builds. */
export function buildSlateReadinessSummary(
  matchReport: Record<string, unknown> | null,
  allTeams: string[],
  pitcherRows: PlayerRow[],
  nativeRows: NativeRankedPlayer[],
  aiRows: AiRankedPlayer[],
  mlCoverage: MlCoverageSummary,
  blueCollarSnapshot: BlueCollarSnapshot | null,
): SlateReadinessSummary {
  // A MISSING match report means every value below that reads it is
  // UNKNOWN -- not zero, and above all never "fully covered". Before
  // this, `teamsAwaiting` defaulted to [] when the document was absent,
  // so lineupsConfirmed computed `uniqueTeams.size - 0` and reported a
  // confident 30/30 teams built entirely out of missing data (confirmed
  // live on the Command Center while the banner alongside it correctly
  // said 15 games had no posted lineup). That also fed
  // computeSlateCompletionStage's `covered >= eligible` branch, so the
  // slate advertised itself as MOSTLY_READY/READY off the same absence.
  // Absence is now propagated as null and rendered as an explicit
  // unknown -- this repo's "fail loudly when critical DFS data is
  // missing / never silently invent missing statistics" rule.
  const hasMatchReport = matchReport !== null && matchReport !== undefined;
  const eligibility = (matchReport?.eligibility as Record<string, number> | undefined) ?? {};
  const teamsAwaiting = (matchReport?.teams_awaiting_lineups as string[] | undefined) ?? [];
  const uniqueTeams = new Set(allTeams);

  return {
    matchReportAvailable: hasMatchReport,
    dkPlayers: hasMatchReport ? ((matchReport?.dk_entries as number) ?? 0) : null,
    identityResolved: hasMatchReport ? ((matchReport?.matched_to_mlb as number) ?? 0) : null,
    startingPitchers: { covered: hasMatchReport ? (eligibility.starting_pitchers ?? 0) : null, eligible: pitcherRows.length },
    lineupsConfirmed: { covered: hasMatchReport ? Math.max(0, uniqueTeams.size - teamsAwaiting.length) : null, eligible: uniqueTeams.size },
    blueCollarUsable: blueCollarSnapshot?.usable_projection_count ?? 0,
    nativeEligible: coverage(nativeRows, (r) => (r as NativeRankedPlayer).nativeProjection !== null),
    aiEligible: coverage(aiRows, (r) => (r as AiRankedPlayer).aiProjection !== null),
    mlEligible: {
      eligible: mlCoverage.eligiblePitchers + mlCoverage.eligibleHitters,
      covered: mlCoverage.projectedPitchers + mlCoverage.projectedHitters,
    },
    optimizerEligible: hasMatchReport ? (eligibility.optimizer_eligible ?? 0) : null,
  };
}

export interface TeamReadinessRow {
  team: string;
  lineupStatus: "CONFIRMED" | "UNCONFIRMED";
  starterStatus: "CONFIRMED" | "PENDING";
  blueCollar: "AVAILABLE" | "PENDING";
  native: "GENERATED" | "PENDING";
  ai: "GENERATED" | "PENDING";
  ml: "GENERATED" | "PENDING";
  ownership: "GENERATED" | "PENDING";
  stackReady: "READY" | "WAITING";
}

/** One row per team on the slate. `stackStatusByTeam` is
 * lib/stacks.ts::buildStackSummaries()'s own output, reused verbatim
 * (never a second stack-readiness computation) -- see this module's
 * own header docstring. `hasOwnership` should be a Set of mlb_player_id
 * strings the ownership snapshot actually covers. */
export function buildTeamReadinessRows(
  allTeams: string[],
  pitcherRows: PlayerRow[],
  hitterRows: PlayerRow[],
  nativeRows: NativeRankedPlayer[],
  aiRows: AiRankedPlayer[],
  blueCollarSnapshot: BlueCollarSnapshot | null,
  hasOwnership: Set<string>,
  stackStatusByTeam: Map<string, "CONFIRMED" | "WAITING_FOR_LINEUP">,
): TeamReadinessRow[] {
  const blueCollarUsableTeams = new Set(
    (blueCollarSnapshot?.players ?? []).filter((p) => p.usable_projection !== null).map((p) => p.team),
  );

  return [...allTeams].sort().map((team) => {
    const teamHitters = hitterRows.filter((r) => r.team === team);
    const teamPitchers = pitcherRows.filter((r) => r.team === team);
    const eligibleTeamRows = [...teamHitters, ...teamPitchers].filter((r) => r.optimizerEligible);

    const anyConfirmedHitter = teamHitters.some((r) => r.eligibilityStatus === "STARTING_HITTER");
    const starterConfirmed = teamPitchers.some((r) => r.eligibilityStatus === "STARTING_PITCHER");

    const nativeEligible = [...nativeRows].filter((r) => r.team === team && r.optimizerEligible);
    const aiEligible = [...aiRows].filter((r) => r.team === team && r.optimizerEligible);

    return {
      team,
      lineupStatus: anyConfirmedHitter ? "CONFIRMED" : "UNCONFIRMED",
      starterStatus: starterConfirmed ? "CONFIRMED" : "PENDING",
      blueCollar: blueCollarUsableTeams.has(team) ? "AVAILABLE" : "PENDING",
      native: nativeEligible.length > 0 && nativeEligible.every((r) => r.nativeProjection !== null) ? "GENERATED" : "PENDING",
      ai: aiEligible.length > 0 && aiEligible.every((r) => r.aiProjection !== null) ? "GENERATED" : "PENDING",
      ml: eligibleTeamRows.length > 0 && eligibleTeamRows.every((r) => r.mlProjection !== null) ? "GENERATED" : "PENDING",
      ownership: eligibleTeamRows.length > 0 && eligibleTeamRows.every((r) => hasOwnership.has(r.id)) ? "GENERATED" : "PENDING",
      stackReady: stackStatusByTeam.get(team) === "CONFIRMED" ? "READY" : "WAITING",
    };
  });
}

export type SlateCompletionStage = "EARLY" | "PARTIAL_LINEUPS" | "MOSTLY_READY" | "READY" | "LOCKED" | "IN_PROGRESS" | "FINAL";

const LIVE_STATUS_SUBSTRINGS = ["in progress", "live", "warmup", "delayed", "manager challenge", "review"];
const FINAL_STATUS_SUBSTRINGS = ["final", "game over", "completed early"];

/** Classified from REAL data only: MLB's own game.status (games.json,
 * verbatim from MLB Stats API's detailedState -- see
 * lib/loaders.ts::loadResearchGames), the earliest DK game lock time
 * (provider slate start times), and lineup-confirmation counts already
 * computed above. Deliberately independent of publish lifecycle status
 * (READY/PARTIAL/ERROR/PUBLISHED, lib/db/slateStatus.ts) -- this is
 * OPERATIONAL readiness, a different axis entirely (see this
 * milestone's own "do not tie this to publish state" instruction). */
export function computeSlateCompletionStage(
  readiness: SlateReadinessSummary,
  games: ResearchGame[],
  earliestLockTimeUtc: string | null,
  nowUtc: string = new Date().toISOString(),
): SlateCompletionStage {
  if (games.length > 0) {
    const statuses = games.map((g) => g.status.toLowerCase());
    if (statuses.every((s) => FINAL_STATUS_SUBSTRINGS.some((f) => s.includes(f)))) return "FINAL";
    if (statuses.some((s) => LIVE_STATUS_SUBSTRINGS.some((l) => s.includes(l)))) return "IN_PROGRESS";
  }

  if (earliestLockTimeUtc && new Date(nowUtc).getTime() >= new Date(earliestLockTimeUtc).getTime()) return "LOCKED";

  const { covered, eligible } = readiness.lineupsConfirmed;
  // covered === null is UNKNOWN lineup coverage (no match report). It can
  // never promote a slate past EARLY -- the previous code compared a
  // fabricated count here and reached MOSTLY_READY/READY on absent data.
  if (covered === null || eligible === 0 || covered === 0) return "EARLY";
  if (covered >= eligible) {
    return (readiness.optimizerEligible ?? 0) > 0 ? "READY" : "MOSTLY_READY";
  }
  return covered / eligible >= 0.5 ? "MOSTLY_READY" : "PARTIAL_LINEUPS";
}
