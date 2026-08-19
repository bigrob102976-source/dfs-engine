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
const TRUSTED_PROVENANCE = new Set(["OFFICIAL_USER_UPLOAD", "AUTHORIZED_PROVIDER"]);

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

export function evaluatePublishReadiness(date: string, slateId: string): PublishReadiness {
  const matchReport = loadLatestDkMatchReport(date, slateId).data;
  const pool = loadLatestDKPlayerPool(date, slateId).data;
  const nativeMap = getNativeProjectionByPlayerId(date);
  const aiMap = getAiProjectionByPlayerId(date);
  const ownership = loadLatestOwnershipSnapshot(date, slateId).data;
  const environment = loadLatestEnvironmentReport(date);

  const provenance = typeof matchReport?.source_provenance === "string" ? (matchReport.source_provenance as string) : null;
  const provenanceOk = provenance !== null && TRUSTED_PROVENANCE.has(provenance);

  const gamesMatched = typeof matchReport?.dk_games_matched_to_research === "number" ? (matchReport.dk_games_matched_to_research as number) : 0;
  const gamesTotal = typeof matchReport?.dk_games_total === "number" ? (matchReport.dk_games_total as number) : 0;
  const gameResolutionOk = gamesTotal > 0 && gamesMatched > 0;

  const poolBuilt = Boolean(pool && pool.players.length > 0);

  const integrity = matchReport?.identity_integrity as { invalid?: number; total?: number } | undefined;
  const integrityOk = poolBuilt && Boolean(integrity) && integrity?.invalid === 0;

  const nativeOk = nativeMap.size > 0;

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
  ];

  const optional: ReadinessCheck[] = [
    { key: "vegas", label: "Vegas", ok: Boolean(environment), detail: environment ? "loaded" : "missing" },
    { key: "ai_projections", label: "AI projections", ok: aiMap.size > 0, detail: aiMap.size > 0 ? `${aiMap.size} players projected` : "missing" },
    { key: "ownership", label: "Ownership", ok: Boolean(ownership), detail: ownership ? "loaded" : "missing" },
  ];

  return { ok: required.every((c) => c.ok), required, optional };
}
