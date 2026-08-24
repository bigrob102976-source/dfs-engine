// Milestone 29: publish-safety gate. Pure read-only evaluation of
// whether a slate's CURRENTLY BUILT artifacts (the "latest" files an
// admin's Process/Refresh just produced -- never anything a member has
// seen) are safe to become the new published version. Never blocks on
// Vegas/AI/Ownership (optional signals) -- those are reported honestly
// as present/missing but never fabricated or treated as blocking, per
// this milestone's explicit "Optional signals may be missing... but must
// display their missing status clearly" requirement.

import { getAiProjectionByPlayerId } from "./aiProjections";
import { loadLatestEnvironmentReport } from "./gameEnvironment";
import { loadLatestDKPlayerPool, loadLatestDkMatchReport, loadLatestOwnershipSnapshot } from "./loaders";
import { getNativeProjectionByPlayerId } from "./nativeProjections";

// Mirrors dfs/providers/source_provenance.py::TRUSTED_FOR_PRODUCTION --
// deliberately a plain constant list, not a re-implementation of the
// classification logic itself (that stays exclusively in Python; this
// only reads the already-computed source_provenance string the Python
// pipeline wrote into the match report).
//
// Milestone 33.2.1 hotfix: this list had drifted out of sync with the
// Python source of truth -- DRAFTKINGS_UNOFFICIAL_LIVE was added to
// TRUSTED_FOR_PRODUCTION by Milestone 32.2B ("DraftKings Unofficial
// Provider is the sole DK slate source going forward, no manual CSV
// step in the production pipeline" -- see that constant's own Python
// docstring) but never propagated here, so every slate built from the
// permanent DK data source was silently blocked from ever reaching
// READY/Publish -- confirmed live via this fix's own test
// (discover.test.ts) and via a real /admin/slates session today.
const TRUSTED_PROVENANCE = new Set(["OFFICIAL_USER_UPLOAD", "AUTHORIZED_PROVIDER", "DRAFTKINGS_UNOFFICIAL_LIVE"]);

export interface ReadinessCheck {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
}

export interface PublishReadiness {
  ok: boolean;
  required: ReadinessCheck[];
  optional: ReadinessCheck[];
}

export async function evaluatePublishReadiness(date: string, slateId: string): Promise<PublishReadiness> {
  const [matchReportLoaded, poolLoaded, nativeMap, aiMap, ownershipLoaded, environment] = await Promise.all([
    loadLatestDkMatchReport(date, slateId),
    loadLatestDKPlayerPool(date, slateId),
    getNativeProjectionByPlayerId(date),
    getAiProjectionByPlayerId(date),
    loadLatestOwnershipSnapshot(date, slateId),
    loadLatestEnvironmentReport(date),
  ]);
  const matchReport = matchReportLoaded.data;
  const pool = poolLoaded.data;
  const ownership = ownershipLoaded.data;

  const provenance = typeof matchReport?.source_provenance === "string" ? (matchReport.source_provenance as string) : null;
  const provenanceOk = provenance !== null && TRUSTED_PROVENANCE.has(provenance);

  const gamesMatched = typeof matchReport?.dk_games_matched_to_research === "number" ? (matchReport.dk_games_matched_to_research as number) : 0;
  const gamesTotal = typeof matchReport?.dk_games_total === "number" ? (matchReport.dk_games_total as number) : 0;
  const gameResolutionOk = gamesTotal > 0 && gamesMatched > 0;

  const poolBuilt = Boolean(pool && pool.players.length > 0);

  const integrity = matchReport?.identity_integrity as { invalid?: number; total?: number } | undefined;
  const integrityOk = poolBuilt && Boolean(integrity) && integrity?.invalid === 0;

  const nativeOk = nativeMap.size > 0;

  // Milestone 31.1: a slate where some (not all) teams' lineups have
  // posted is a distinct, expected-early-in-the-day state -- never
  // silently READY (a late scratch/lineup swap on an unconfirmed team
  // could still change), and never a generic ERROR either. Sourced
  // from dfs/eligibility.py's LINEUP_UNCONFIRMED via the match report's
  // teams_awaiting_lineups (dfs/player_pool.py::build_match_report) --
  // never DK's own "Starting" column, which is only a copy of the real
  // MLB-sourced lineup our research pipeline already tracks.
  const teamsAwaitingLineups = Array.isArray(matchReport?.teams_awaiting_lineups)
    ? (matchReport.teams_awaiting_lineups as string[])
    : [];
  // No match report at all means "unknown," not "vacuously confirmed" --
  // must not report ok:true just because there's nothing to list yet.
  const lineupsConfirmedOk = matchReport !== null && teamsAwaitingLineups.length === 0;

  const required: ReadinessCheck[] = [
    {
      key: "source_provenance", label: "Trusted DK source provenance", ok: provenanceOk,
      detail: provenance ?? "unknown -- no match report found",
    },
    {
      key: "game_resolution", label: "Valid game resolution", ok: gameResolutionOk,
      detail: `${gamesMatched}/${gamesTotal} DK games matched to research`,
    },
    {
      key: "player_pool", label: "Player pool built", ok: poolBuilt,
      detail: poolBuilt ? `${pool!.players.length} players` : "no player pool found",
    },
    {
      key: "pool_integrity", label: "Player pool integrity passed", ok: Boolean(integrityOk),
      detail: integrity ? `${integrity.invalid ?? 0} invalid identity row(s) of ${integrity.total ?? 0}` : "not checked",
    },
    {
      key: "native_projections", label: "Native projections available", ok: nativeOk,
      detail: nativeOk ? `${nativeMap.size} players projected` : "no native projection snapshot found",
    },
    {
      key: "lineup_confirmation", label: "All lineups confirmed", ok: lineupsConfirmedOk,
      detail: lineupsConfirmedOk
        ? "every team's lineup has posted"
        : matchReport === null
          ? "unknown -- no match report found"
          : `AWAITING LINEUPS: ${teamsAwaitingLineups.join(", ")}`,
    },
  ];

  const optional: ReadinessCheck[] = [
    { key: "vegas", label: "Vegas", ok: Boolean(environment), detail: environment ? "loaded" : "missing" },
    { key: "ai_projections", label: "AI projections", ok: aiMap.size > 0, detail: aiMap.size > 0 ? `${aiMap.size} players projected` : "missing" },
    { key: "ownership", label: "Ownership", ok: Boolean(ownership), detail: ownership ? "loaded" : "missing" },
  ];

  return { ok: required.every((c) => c.ok), required, optional };
}
