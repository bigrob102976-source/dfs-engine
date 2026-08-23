import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { getAiProjectionByPlayerId } from "../aiProjections";
import { safeReadJson } from "../discovery";
import { getProjectionComparisonByPlayerId } from "../externalProjections";
import { getFantasyProsProjectionByPlayerId } from "../fantasyProsProjections";
import { getBigMoneyMlProvenance, getMlProjectionByPlayerId } from "../mlProjections";
import { getNativeProjectionByPlayerId } from "../nativeProjections";
import { fingerprintChanged, lineupSetFingerprint } from "../orchestrator/artifacts";
import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import type { LineupSet } from "../types";
import { parseLastJsonLine } from "./jsonLine";
import { getCachedPoolPath } from "./poolCache";
import type { OptimizerBuildRequest, OptimizerBuildResult } from "./types";

/** Milestone 17's Projection Source selector: "independent" (the
 * default -- Big Money's own projections, exactly as before this
 * milestone) never writes anything and passes no extra flag, so that
 * path is byte-identical to pre-M17 behavior. "external"/"adjusted"/"ai"/
 * "native"/"fantasypros" write a small, ephemeral {mlb_player_id:
 * {projection, ceiling, floor}} JSON file under the OS temp directory and
 * pass it via --projection-overrides -- the persisted
 * dk_player_pool_<ts>.json (Big Money's independent projections) is NEVER
 * written to. A player missing from the chosen source simply has no
 * override entry, so scripts/optimize_dk_lineups.py falls back to their
 * independent value rather than dropping them. Milestone 20: "ai" supplies
 * its own ceiling/floor (projection_engine/scoring.py computes both);
 * Milestone 23: "native" does too (native_projections/uncertainty.py) --
 * external/adjusted/fantasypros leave those two null, so the optimizer
 * falls back to the pool's own independent ceiling/floor for those three
 * (FantasyPros' public API never returns a ceiling/floor, only a single
 * expected-value projection -- see fantasypros/models.py). Selecting
 * "fantasypros" changes ONLY the projection source; eligibility, salary,
 * positions, Vegas, ownership, constraints, and stacks are untouched --
 * getFantasyProsProjectionByPlayerId already only contains MATCHED
 * players, so an unmatched/off-slate player is simply absent here too.
 *
 * Milestone 32.4: "big_money_ml" is DIFFERENT from every source above --
 * see isStrictProjectionSource below. It still writes the same override
 * shape (only players with a genuinely valid, pregame-captured ML
 * projection get an entry -- MISSING/INVALID_FEATURE_PARITY rows are
 * never included, same discipline as the Projection Lab's ML column),
 * but scripts/optimize_dk_lineups.py is told (via --strict-projection-
 * source) to EXCLUDE any optimizer-eligible player who has no entry
 * here, rather than falling back to their independent projection --
 * "ML-only means ML-only," never a hidden mixture of sources. */
export function isStrictProjectionSource(source: OptimizerBuildRequest["projectionSource"]): boolean {
  return source === "big_money_ml";
}

function writeProjectionOverridesFile(request: OptimizerBuildRequest): string | null {
  if (request.projectionSource === "independent") return null;

  const overrides: Record<string, { projection: number | null; ceiling: number | null; floor: number | null }> = {};

  if (request.projectionSource === "ai") {
    const aiByPlayerId = getAiProjectionByPlayerId(request.date);
    for (const [mlbPlayerId, player] of aiByPlayerId) {
      if (player.ai_projection === null) continue;
      overrides[mlbPlayerId] = { projection: player.ai_projection, ceiling: player.ai_ceiling, floor: player.ai_floor };
    }
  } else if (request.projectionSource === "native") {
    const nativeByPlayerId = getNativeProjectionByPlayerId(request.date);
    for (const [mlbPlayerId, player] of nativeByPlayerId) {
      overrides[mlbPlayerId] = { projection: player.native_projection, ceiling: player.native_ceiling, floor: player.native_floor };
    }
  } else if (request.projectionSource === "fantasypros") {
    const fantasyProsByPlayerId = getFantasyProsProjectionByPlayerId(request.date);
    for (const [mlbPlayerId, player] of fantasyProsByPlayerId) {
      if (player.dk_points === null) continue;
      overrides[mlbPlayerId] = { projection: player.dk_points, ceiling: null, floor: null };
    }
  } else if (request.projectionSource === "big_money_ml") {
    const mlByPlayerId = getMlProjectionByPlayerId(request.date);
    for (const [mlbPlayerId, player] of mlByPlayerId) {
      if (player.projection === null) continue;
      if (player.projection_status !== "LIVE_PREGAME" && player.projection_status !== "PREGAME_FROZEN") continue;
      // No ML ceiling/floor exists (the frozen models output a point
      // projection only) -- left null so scripts/optimize_dk_lineups.py
      // falls back to the pool's own independent ceiling/floor, same
      // documented exception FantasyPros already uses above. Only the
      // PROJECTION value itself is held to strict source purity.
      overrides[mlbPlayerId] = { projection: player.projection, ceiling: null, floor: null };
    }
  } else {
    const comparisonByPlayerId = getProjectionComparisonByPlayerId(request.date);
    for (const [mlbPlayerId, row] of comparisonByPlayerId) {
      const projection = request.projectionSource === "external" ? row.externalProjection : row.adjustedProjection;
      if (projection === null) continue;
      overrides[mlbPlayerId] = { projection, ceiling: null, floor: null };
    }
  }
  // Milestone 32.4: an empty ML overrides map must still produce an
  // (empty) file rather than null -- returning null here would make
  // buildArgv omit --projection-overrides entirely, and combined with
  // --strict-projection-source that would mean "no overrides file
  // loaded" reads as an empty dict either way, so this is actually safe
  // either way -- but writing the empty file keeps the on-disk record
  // honest about which source was actually selected for this build.
  if (Object.keys(overrides).length === 0 && !isStrictProjectionSource(request.projectionSource)) return null;

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-projection-overrides-"));
  const filePath = path.join(dir, "overrides.json");
  fs.writeFileSync(filePath, JSON.stringify(overrides), "utf-8");
  return filePath;
}

function cleanupProjectionOverridesFile(filePath: string | null): void {
  if (!filePath) return;
  try {
    fs.rmSync(path.dirname(filePath), { recursive: true, force: true });
  } catch {
    // Best-effort cleanup of an OS temp file -- never fail a build over this.
  }
}

function buildArgv(
  request: OptimizerBuildRequest, poolPath: string, ownershipPath: string | null, projectionOverridesPath: string | null, extra: string[],
): string[] {
  const args: string[] = ["--date", request.date, "--pool", poolPath];
  if (ownershipPath) args.push("--ownership", ownershipPath);
  if (projectionOverridesPath) args.push("--projection-overrides", projectionOverridesPath);
  args.push("--projection-source", request.projectionSource);
  if (isStrictProjectionSource(request.projectionSource)) {
    args.push("--strict-projection-source");
    const provenance = getBigMoneyMlProvenance(request.date);
    if (provenance.pitcherModelVersion) args.push("--pitcher-model-version", provenance.pitcherModelVersion);
    if (provenance.hitterModelVersion) args.push("--hitter-model-version", provenance.hitterModelVersion);
    if (provenance.pitcherSnapshotGeneratedAt) args.push("--pitcher-projection-snapshot-generated-at", provenance.pitcherSnapshotGeneratedAt);
    if (provenance.hitterSnapshotGeneratedAt) args.push("--hitter-projection-snapshot-generated-at", provenance.hitterSnapshotGeneratedAt);
  }
  args.push("--lineups", String(request.lineups));
  args.push("--objective", request.objective);
  args.push("--min-unique", String(request.minUnique));
  if (request.stackSize != null) args.push("--stack-size", String(request.stackSize));
  if (request.stackTeam) args.push("--stack-team", request.stackTeam);
  for (const name of request.locks) args.push("--lock", name);
  for (const name of request.exclusions) args.push("--exclude", name);
  for (const [name, fraction] of Object.entries(request.maxExposure)) {
    if (fraction < 1) args.push("--max-exposure", `${name}=${fraction}`);
  }
  if (request.minConfidence != null) args.push("--min-confidence", String(request.minConfidence));
  if (request.maxPlayerRisk != null) args.push("--max-player-risk", String(request.maxPlayerRisk));
  if (request.minSalary != null) args.push("--min-salary", String(request.minSalary));
  if (request.allowPitcherVsHitter) args.push("--allow-pitcher-vs-hitter");
  args.push("--interactive"); // config.optimizer_config.INTERACTIVE_SOLVER_MAX_TIME_SECONDS, not the 30s batch default
  args.push(...extra);
  return args;
}

function extractConfigurationError(stdout: string): string | null {
  const match = stdout.match(/CONFIGURATION ERROR: (.+)/);
  return match ? match[1].trim() : null;
}

/** Authoritative pre-solve validation: runs the SAME resolve_settings()/
 * pre_solve_diagnostics() logic the real optimizer uses (see
 * optimizer/constraints.py) via `--validate-only`, which never invokes
 * the CP-SAT solver. Returns [] when nothing was found wrong -- not a
 * feasibility guarantee, just the absence of a cheaply-detectable blocker. */
export async function validateBuildRequest(request: OptimizerBuildRequest): Promise<string[]> {
  const cached = getCachedPoolPath(request.date, request.slateId);
  if (!cached) {
    return ["No player pool loaded for this slate yet -- select a slate first."];
  }
  const overridesPath = writeProjectionOverridesFile(request);
  try {
    const args = buildArgv(request, cached.poolPath, cached.ownershipPath, overridesPath, ["--validate-only"]);
    const result = await runPythonScript("scripts/optimize_dk_lineups.py", args);
    const doc = parseLastJsonLine(result.stdout);
    if (!doc) {
      return [`Unexpected validation failure: ${tail(result.stdout + result.stderr, 500)}`];
    }
    return Array.isArray(doc.errors) ? (doc.errors as string[]) : [];
  } finally {
    cleanupProjectionOverridesFile(overridesPath);
  }
}

/** Runs the real interactive build: a fast authoritative pre-check
 * first (skips the solver entirely if already invalid), then the real
 * CP-SAT solve via scripts/optimize_dk_lineups.py --interactive, which
 * persists an immutable lineup set exactly like every other optimizer
 * run in this project (optimizer/persistence.py) -- the dashboard never
 * bypasses that. */
export async function buildLineups(request: OptimizerBuildRequest): Promise<OptimizerBuildResult> {
  const startedAt = Date.now();
  const cached = getCachedPoolPath(request.date, request.slateId);
  if (!cached) {
    return {
      ok: false,
      errors: ["No player pool loaded for this slate yet -- select a slate first."],
      lineupSetPath: null,
      csvPath: null,
      lineupsRequested: request.lineups,
      lineupsGenerated: 0,
      stoppedReason: null,
      lineups: [],
      elapsedMs: Date.now() - startedAt,
      excludedMissingProjectionSource: [],
    };
  }

  const preErrors = await validateBuildRequest(request);
  if (preErrors.length > 0) {
    return {
      ok: false,
      errors: preErrors,
      lineupSetPath: null,
      csvPath: null,
      lineupsRequested: request.lineups,
      lineupsGenerated: 0,
      stoppedReason: null,
      lineups: [],
      elapsedMs: Date.now() - startedAt,
      excludedMissingProjectionSource: [],
    };
  }

  const before = lineupSetFingerprint(request.date);
  const overridesPath = writeProjectionOverridesFile(request);
  let result;
  try {
    const args = buildArgv(request, cached.poolPath, cached.ownershipPath, overridesPath, []);
    result = await runPythonScript("scripts/optimize_dk_lineups.py", args);
  } finally {
    cleanupProjectionOverridesFile(overridesPath);
  }
  const after = lineupSetFingerprint(request.date);
  const elapsedMs = Date.now() - startedAt;

  if (result.exitCode !== 0 || !fingerprintChanged(before, after) || !after.path) {
    const configError = extractConfigurationError(result.stdout);
    return {
      ok: false,
      errors: [configError ?? `Build failed: ${tail(result.stdout + result.stderr, 1000)}`],
      lineupSetPath: null,
      csvPath: null,
      lineupsRequested: request.lineups,
      lineupsGenerated: 0,
      stoppedReason: null,
      lineups: [],
      elapsedMs,
      excludedMissingProjectionSource: [],
    };
  }

  const doc = safeReadJson<LineupSet>(after.path);
  const csvPath = after.path.replace(/\.json$/, ".csv");

  return {
    ok: true,
    errors: [],
    lineupSetPath: after.path,
    csvPath: fs.existsSync(csvPath) ? csvPath : null,
    lineupsRequested: doc?.lineups_requested ?? request.lineups,
    lineupsGenerated: doc?.lineups_generated ?? 0,
    stoppedReason: doc?.stopped_reason ?? null,
    lineups: doc?.lineups ?? [],
    elapsedMs,
    excludedMissingProjectionSource: doc?.excluded_missing_projection_source ?? [],
  };
}
