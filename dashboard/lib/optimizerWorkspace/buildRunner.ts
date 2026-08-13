import fs from "node:fs";

import { safeReadJson } from "../discovery";
import { fingerprintChanged, lineupSetFingerprint } from "../orchestrator/artifacts";
import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import type { LineupSet } from "../types";
import { parseLastJsonLine } from "./jsonLine";
import { getCachedPoolPath } from "./poolCache";
import type { OptimizerBuildRequest, OptimizerBuildResult } from "./types";

function buildArgv(request: OptimizerBuildRequest, poolPath: string, ownershipPath: string | null, extra: string[]): string[] {
  const args: string[] = ["--date", request.date, "--pool", poolPath];
  if (ownershipPath) args.push("--ownership", ownershipPath);
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
  const args = buildArgv(request, cached.poolPath, cached.ownershipPath, ["--validate-only"]);
  const result = await runPythonScript("scripts/optimize_dk_lineups.py", args);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc) {
    return [`Unexpected validation failure: ${tail(result.stdout + result.stderr, 500)}`];
  }
  return Array.isArray(doc.errors) ? (doc.errors as string[]) : [];
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
    };
  }

  const before = lineupSetFingerprint(request.date);
  const args = buildArgv(request, cached.poolPath, cached.ownershipPath, []);
  const result = await runPythonScript("scripts/optimize_dk_lineups.py", args);
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
  };
}
