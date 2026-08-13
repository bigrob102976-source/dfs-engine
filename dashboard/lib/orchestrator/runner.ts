import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { ARTIFACT_DIRS, artifactPath } from "../artifactRoot";
import { getTodayChicagoDate } from "../currentDate";
import { safeReadJson } from "../discovery";
import type { BatterSnapshot, DKPlayerPool, PitcherSnapshot, SlateIndex } from "../types";
import {
  batterSnapshotFingerprint,
  fingerprintChanged,
  lineupSetFingerprint,
  matchReportFingerprint,
  ownershipFingerprint,
  pitcherSnapshotFingerprint,
  poolFingerprint,
  providerSlateFingerprint,
  researchSlateFingerprint,
  type Fingerprint,
} from "./artifacts";
import { buildChangeReport } from "./changeReport";
import { runPythonScript, tail } from "./pythonRunner";
import { initialSteps, STEP_DEFINITIONS } from "./steps";
import type { PipelineStepId, RunOutcome, RunState, SlateOption, StepStatus } from "./types";

// --------------------------------------------------------------------------
// Disk-persisted run state (crash visibility + cross-request GET status).
// In-memory `activeRun`/`lastCompletedRun` below is the source of truth
// while this Node process is alive; these files just make that state
// inspectable/testable without a database, and give the GET endpoint
// something to show after a dev-server restart. Kept inside dashboard/,
// not the Python artifact tree -- it's dashboard operational state, not
// a pipeline artifact.
// --------------------------------------------------------------------------

function getRunStateDir(): string {
  return process.env.MLB_DFS_RUNSTATE_DIR ? path.resolve(process.env.MLB_DFS_RUNSTATE_DIR) : path.join(process.cwd(), ".runstate");
}

function getCurrentRunStateFile(): string {
  return path.join(getRunStateDir(), "current_run.json");
}

function getLastCompletedRunStateFile(): string {
  return path.join(getRunStateDir(), "last_completed_run.json");
}

function persistRunState(state: RunState): void {
  const dir = getRunStateDir();
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(getCurrentRunStateFile(), JSON.stringify(state, null, 2), "utf-8");
}

function readPersistedCurrentRun(): RunState | null {
  try {
    return JSON.parse(fs.readFileSync(getCurrentRunStateFile(), "utf-8")) as RunState;
  } catch {
    return null;
  }
}

function persistLastCompletedRun(state: RunState): void {
  const dir = getRunStateDir();
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(getLastCompletedRunStateFile(), JSON.stringify(state, null, 2), "utf-8");
}

function readPersistedLastCompletedRun(): RunState | null {
  try {
    return JSON.parse(fs.readFileSync(getLastCompletedRunStateFile(), "utf-8")) as RunState;
  } catch {
    return null;
  }
}

// --------------------------------------------------------------------------
// In-memory concurrency lock (single Node process). `activeRun` is set
// while a run is "running" or paused "needs_selection"; cleared once it
// reaches a terminal state, allowing the next refresh click to start.
// --------------------------------------------------------------------------

let activeRun: RunState | null = null;
let lastCompletedRun: RunState | null = null;
let activeRunPromise: Promise<void> | null = null;

/** Exposed for tests only -- resets module-level state between cases. */
export function __resetOrchestratorStateForTests(): void {
  activeRun = null;
  lastCompletedRun = null;
  activeRunPromise = null;
}

/** Exposed for tests only -- since startRefresh()/resumeWithSlateSelection()
 * fire the pipeline without awaiting it (a real refresh can take minutes),
 * tests that inject a fast fake Python runner need a way to wait for the
 * whole run to actually settle before asserting on the final state. */
export async function __waitForActiveRunToSettleForTests(): Promise<void> {
  if (activeRunPromise) await activeRunPromise;
}

export function getCurrentRun(): RunState | null {
  if (activeRun) return activeRun;
  if (lastCompletedRun) return lastCompletedRun;
  return readPersistedCurrentRun();
}

function findStep(state: RunState, id: PipelineStepId) {
  const step = state.steps.find((s) => s.id === id);
  if (!step) throw new Error(`Unknown pipeline step id: ${id}`);
  return step;
}

function markStepStatus(state: RunState, id: PipelineStepId, status: StepStatus, patch: Partial<RunState["steps"][number]> = {}) {
  const step = findStep(state, id);
  Object.assign(step, { status, ...patch });
  state.currentStepId = status === "running" ? id : state.currentStepId;
  persistRunState(state);
}

/** Runs one Python CLI step and marks it ready/failed based on whether
 * exit code was 0 AND the step's own artifact actually changed -- see
 * artifacts.ts for why exit code alone isn't sufficient. */
async function runStep(
  state: RunState,
  id: PipelineStepId,
  scriptPath: string,
  args: string[],
  fingerprintFn: (date: string) => Fingerprint,
): Promise<{ ok: boolean; artifactPath: string | null }> {
  const before = fingerprintFn(state.slateDate);
  markStepStatus(state, id, "running", { startedAt: new Date().toISOString(), command: ["python", scriptPath, ...args] });

  const result = await runPythonScript(scriptPath, args);
  const after = fingerprintFn(state.slateDate);
  const ok = result.exitCode === 0 && fingerprintChanged(before, after);

  markStepStatus(state, id, ok ? "ready" : "failed", {
    finishedAt: new Date().toISOString(),
    artifactPath: after.path,
    stdoutTail: tail(result.stdout),
    stderrTail: tail(result.stderr),
    message: ok
      ? null
      : result.exitCode !== 0
        ? `Script exited with code ${result.exitCode}.`
        : "Script completed but produced no new artifact.",
  });

  return { ok, artifactPath: after.path };
}

type LineupCounts = { projection: number | null; balanced: number | null; leverage: number | null };
type LineupSetPaths = { projection: string | null; balanced: string | null; leverage: string | null };

const EMPTY_LINEUP_COUNTS: LineupCounts = { projection: null, balanced: null, leverage: null };
const EMPTY_LINEUP_PATHS: LineupSetPaths = { projection: null, balanced: null, leverage: null };

function finalize(
  state: RunState,
  status: RunState["status"],
  outcome: RunOutcome,
  error?: string,
  lineupCounts: LineupCounts = EMPTY_LINEUP_COUNTS,
  lineupSetPaths: LineupSetPaths = EMPTY_LINEUP_PATHS,
) {
  state.status = status;
  state.outcome = outcome;
  state.finishedAt = new Date().toISOString();
  if (error) state.error = error;
  if (status !== "needs_selection") {
    state.currentStepId = null;
    for (const step of state.steps) {
      if (step.status === "waiting" || step.status === "running") step.status = "skipped";
    }
  }

  if (status === "completed") {
    state.summary = buildRunSummary(state, lineupCounts, lineupSetPaths);
    const previous = lastCompletedRun ?? readPersistedLastCompletedRun();
    state.changeReport = buildChangeReport(previous, state);
    lastCompletedRun = state;
    persistLastCompletedRun(state);
  }

  persistRunState(state);
  activeRun = status === "needs_selection" ? state : null;
}

function buildRunSummary(state: RunState, lineupCounts: LineupCounts, lineupSetPaths: LineupSetPaths): RunState["summary"] {
  const date = state.slateDate;
  const slate = safeReadJson<SlateIndex>(artifactPath(ARTIFACT_DIRS.research, date, "slate.json"));
  const pitcherSnap = safeReadJson<PitcherSnapshot>(findStep(state, "pitchers").artifactPath);
  const batterSnap = safeReadJson<BatterSnapshot>(findStep(state, "batters").artifactPath);
  const pool = safeReadJson<DKPlayerPool>(findStep(state, "playerPool").artifactPath);
  const matchReport = safeReadJson<Record<string, unknown>>(matchReportFingerprint(date).path);
  const providerSlate = safeReadJson<Record<string, unknown>>(findStep(state, "dfsSalaries").artifactPath);

  const distinctGamesWithLineups = new Set((batterSnap?.hitters ?? []).map((h) => h.game_id)).size;

  return {
    slateDate: date,
    mlbGames: slate?.counts?.games ?? null,
    dfsGames: typeof matchReport?.dk_games_total === "number" ? (matchReport.dk_games_total as number) : null,
    postedLineups: distinctGamesWithLineups,
    missingLineups: batterSnap?.missing_lineup_game_ids?.length ?? null,
    pitcherCount: pitcherSnap?.pitcher_count ?? null,
    hitterCount: batterSnap?.hitter_count ?? null,
    salaryCoveragePercent: typeof matchReport?.salary_coverage_percent === "number" ? (matchReport.salary_coverage_percent as number) : null,
    positionCoveragePercent:
      typeof matchReport?.position_coverage_percent === "number" ? (matchReport.position_coverage_percent as number) : null,
    dkEntries: typeof matchReport?.dk_entries === "number" ? (matchReport.dk_entries as number) : null,
    matchedToMlb: typeof matchReport?.matched_to_mlb === "number" ? (matchReport.matched_to_mlb as number) : null,
    unmatchedCount: typeof matchReport?.unmatched_count === "number" ? (matchReport.unmatched_count as number) : null,
    rosterFeasibilityPass: pool?.roster_feasibility_pass ?? null,
    ownershipReady: findStep(state, "ownership").status === "ready",
    lineupCounts,
    lineupSetPaths,
    providerName: typeof providerSlate?.provider_name === "string" ? (providerSlate.provider_name as string) : null,
    isMock: Boolean(providerSlate?.is_mock),
    providerSource:
      providerSlate?.source === "explicit" || providerSlate?.source === "automatic_fallback"
        ? (providerSlate.source as "explicit" | "automatic_fallback")
        : null,
    selectedSlateId: typeof providerSlate?.selected_slate_id === "string" ? (providerSlate.selected_slate_id as string) : null,
  };
}

async function runDfsSalariesStep(
  state: RunState,
  slateId: string | undefined,
): Promise<{ status: string; doc: Record<string, unknown> | null; path: string | null }> {
  const args = ["--date", state.slateDate];
  if (slateId) args.push("--slate-id", slateId);

  markStepStatus(state, "dfsSalaries", "running", {
    startedAt: new Date().toISOString(),
    command: ["python", "scripts/fetch_dfs_slate.py", ...args],
  });

  const before = providerSlateFingerprint(state.slateDate);
  const result = await runPythonScript("scripts/fetch_dfs_slate.py", args);
  const after = providerSlateFingerprint(state.slateDate);

  if (result.exitCode !== 0 || !fingerprintChanged(before, after)) {
    // fetch_dfs_slate.py is designed to always write an artifact and exit 0 --
    // if that didn't happen, don't trust whatever an earlier run may have left
    // behind at `after.path`; report the unexpected failure directly instead.
    markStepStatus(state, "dfsSalaries", "failed", {
      finishedAt: new Date().toISOString(),
      artifactPath: after.path,
      stdoutTail: tail(result.stdout),
      stderrTail: tail(result.stderr),
      message: `Unexpected script failure (exit ${result.exitCode}).`,
    });
    return { status: "unavailable", doc: null, path: after.path };
  }

  const doc = safeReadJson<Record<string, unknown>>(after.path);
  const status = (doc?.status as string | undefined) ?? "unavailable";

  if (status === "ready") {
    const players = Array.isArray(doc?.players) ? (doc!.players as unknown[]).length : 0;
    markStepStatus(state, "dfsSalaries", "ready", {
      finishedAt: new Date().toISOString(),
      artifactPath: after.path,
      message: `Slate: ${doc?.selected_slate_id ?? "?"} (${players} players)`,
    });
  } else if (status === "needs_selection") {
    markStepStatus(state, "dfsSalaries", "needs_input", {
      finishedAt: new Date().toISOString(),
      artifactPath: after.path,
      message: "Multiple DFS slates available -- selection required.",
    });
  } else {
    markStepStatus(state, "dfsSalaries", "failed", {
      finishedAt: new Date().toISOString(),
      artifactPath: after.path,
      message: (doc?.reason as string | undefined) ?? `DFS salary provider status: ${status}`,
    });
  }

  return { status, doc, path: after.path };
}

const DFS_STATUS_TO_OUTCOME: Record<string, RunOutcome> = {
  not_connected: "dfs_not_connected",
  unavailable: "dfs_unavailable",
  auth_failed: "dfs_auth_failed",
  no_slate: "dfs_no_slate",
  invalid_slate_id: "dfs_invalid_slate_id",
};

const OPTIMIZER_OBJECTIVES: ReadonlyArray<{ key: "projection" | "balanced" | "leverage"; flag: string; label: string }> = [
  { key: "projection", flag: "projection", label: "Projection" },
  { key: "balanced", flag: "balanced", label: "Balanced" },
  { key: "leverage", flag: "leverage", label: "Leverage" },
];

async function runOptimizerStep(
  state: RunState,
  poolPath: string,
  ownershipPath: string | null,
): Promise<{ ok: boolean; lineupCounts: LineupCounts; lineupSetPaths: LineupSetPaths }> {
  markStepStatus(state, "optimizer", "running", { startedAt: new Date().toISOString() });

  const lineupCounts: LineupCounts = { projection: null, balanced: null, leverage: null };
  const lineupSetPaths: LineupSetPaths = { projection: null, balanced: null, leverage: null };
  let allOk = true;
  const failures: string[] = [];
  let lastStdout = "";
  let lastStderr = "";
  let lastCommand: string[] = [];
  let lastArtifactPath: string | null = null;

  for (let i = 0; i < OPTIMIZER_OBJECTIVES.length; i++) {
    const objective = OPTIMIZER_OBJECTIVES[i];
    // Lineup filenames are second-resolution timestamps and refuse to overwrite --
    // stagger sequential runs so three back-to-back solves (which can finish inside
    // the same second on a fast machine / small slate) never collide.
    if (i > 0) await new Promise((resolve) => setTimeout(resolve, 1100));

    const args = ["--date", state.slateDate, "--pool", poolPath, "--lineups", "20", "--min-unique", "2", "--objective", objective.flag];
    if (ownershipPath) args.push("--ownership", ownershipPath);

    const before = lineupSetFingerprint(state.slateDate);
    const result = await runPythonScript("scripts/optimize_dk_lineups.py", args);
    const after = lineupSetFingerprint(state.slateDate);
    const ok = result.exitCode === 0 && fingerprintChanged(before, after);

    lastStdout = result.stdout;
    lastStderr = result.stderr;
    lastCommand = ["python", "scripts/optimize_dk_lineups.py", ...args];
    lastArtifactPath = after.path;

    if (ok && after.path) {
      lineupSetPaths[objective.key] = after.path;
      const doc = safeReadJson<Record<string, unknown>>(after.path);
      lineupCounts[objective.key] = typeof doc?.lineups_generated === "number" ? (doc.lineups_generated as number) : null;
    } else {
      allOk = false;
      failures.push(objective.label);
    }
  }

  markStepStatus(state, "optimizer", allOk ? "ready" : "failed", {
    finishedAt: new Date().toISOString(),
    artifactPath: lastArtifactPath,
    command: lastCommand,
    stdoutTail: tail(lastStdout),
    stderrTail: tail(lastStderr),
    message: allOk
      ? `Projection: ${lineupCounts.projection ?? 0}, Balanced: ${lineupCounts.balanced ?? 0}, Leverage: ${lineupCounts.leverage ?? 0} lineups.`
      : `Failed objective(s): ${failures.join(", ")}.`,
  });

  return { ok: allOk, lineupCounts, lineupSetPaths };
}

async function continueAfterDfsSalaries(state: RunState) {
  const poolResult = await runStep(state, "playerPool", "scripts/build_dfs_pool_from_provider.py", ["--date", state.slateDate], poolFingerprint);
  if (!poolResult.ok || !poolResult.artifactPath) {
    finalize(state, "failed", "player_matching_failure", "Player pool build failed or produced no pool.");
    return;
  }

  const pool = safeReadJson<DKPlayerPool>(poolResult.artifactPath);
  const matchReport = safeReadJson<Record<string, unknown>>(matchReportFingerprint(state.slateDate).path);
  const matchedToMlb = typeof matchReport?.matched_to_mlb === "number" ? (matchReport.matched_to_mlb as number) : null;

  if (matchedToMlb === 0) {
    findStep(state, "playerPool").message = "Zero DFS entries matched to MLB identities.";
    finalize(state, "failed", "player_matching_failure", "Zero DFS entries matched to MLB identities.");
    return;
  }
  if (!pool?.roster_feasibility_pass) {
    findStep(state, "playerPool").message = "Matched pool cannot fill a legal roster (roster feasibility FAILED).";
    finalize(state, "failed", "roster_infeasible", "Matched pool cannot fill a legal DK roster.");
    return;
  }

  const ownershipResult = await runStep(state, "ownership", "scripts/project_dk_ownership.py", ["--date", state.slateDate, "--pool", poolResult.artifactPath], ownershipFingerprint);
  if (!ownershipResult.ok) {
    finalize(state, "failed", "ownership_failure", "Ownership projection failed or produced no snapshot.");
    return;
  }

  const optimizer = await runOptimizerStep(state, poolResult.artifactPath, ownershipResult.artifactPath);
  if (!optimizer.ok) {
    finalize(
      state,
      "failed",
      "optimizer_infeasible",
      "One or more optimizer objectives failed to produce lineups.",
      optimizer.lineupCounts,
      optimizer.lineupSetPaths,
    );
    return;
  }

  finalize(state, "completed", "ready", undefined, optimizer.lineupCounts, optimizer.lineupSetPaths);
}

async function executeRun(state: RunState, resumeSlateId?: string) {
  try {
    if (!resumeSlateId) {
      const research = await runStep(state, "research", "scripts/build_research_package.py", ["--date", state.slateDate], researchSlateFingerprint);
      if (!research.ok) {
        finalize(state, "failed", "mlb_data_failure", "Research package build failed.");
        return;
      }

      const pitchers = await runStep(state, "pitchers", "scripts/run_real_pitcher_agent.py", ["--date", state.slateDate], pitcherSnapshotFingerprint);
      if (!pitchers.ok) {
        finalize(state, "failed", "pitcher_agent_failure", "Pitcher Agent run failed.");
        return;
      }

      const batters = await runStep(state, "batters", "scripts/run_real_batter_agent.py", ["--date", state.slateDate], batterSnapshotFingerprint);
      if (!batters.ok) {
        finalize(state, "failed", "batter_agent_failure", "Batter Agent run failed.");
        return;
      }
    }

    const dfsResult = await runDfsSalariesStep(state, resumeSlateId);

    if (dfsResult.status === "needs_selection") {
      const slates = Array.isArray(dfsResult.doc?.slates) ? (dfsResult.doc!.slates as Record<string, unknown>[]) : [];
      const options: SlateOption[] = slates.map((s) => ({
        slateId: String(s.slate_id),
        slateName: (s.slate_name as string | null) ?? null,
        gameCount: (s.game_count as number | null) ?? null,
        startTime: (s.start_time as string | null) ?? null,
      }));
      state.slateOptions = options;
      state.status = "needs_selection";
      state.outcome = "needs_slate_selection";
      state.currentStepId = null;
      persistRunState(state);
      activeRun = state;
      return;
    }

    if (dfsResult.status !== "ready") {
      const outcome = DFS_STATUS_TO_OUTCOME[dfsResult.status] ?? "dfs_unavailable";
      finalize(state, "failed", outcome, (dfsResult.doc?.reason as string | undefined) ?? `DFS provider status: ${dfsResult.status}`);
      return;
    }

    await continueAfterDfsSalaries(state);
  } catch (err) {
    finalize(state, "failed", "unexpected_error", err instanceof Error ? err.message : String(err));
  }
}

export interface StartRefreshResult {
  accepted: boolean;
  conflict: boolean;
  run: RunState;
}

export function startRefresh(): StartRefreshResult {
  if (activeRun && (activeRun.status === "running" || activeRun.status === "needs_selection")) {
    return { accepted: false, conflict: true, run: activeRun };
  }

  const state: RunState = {
    runId: crypto.randomUUID(),
    slateDate: getTodayChicagoDate(),
    status: "running",
    outcome: null,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    currentStepId: null,
    steps: initialSteps(),
    slateOptions: null,
    summary: null,
    changeReport: null,
    error: null,
  };

  activeRun = state;
  persistRunState(state);
  activeRunPromise = executeRun(state);

  return { accepted: true, conflict: false, run: state };
}

export interface ResumeResult {
  ok: boolean;
  error?: string;
  run?: RunState;
}

export function resumeWithSlateSelection(slateId: string): ResumeResult {
  if (!activeRun || activeRun.status !== "needs_selection") {
    return { ok: false, error: "No paused run is awaiting slate selection." };
  }
  const valid = (activeRun.slateOptions ?? []).some((o) => o.slateId === slateId);
  if (!valid) {
    return { ok: false, error: `"${slateId}" is not one of the discovered slate options for this run.` };
  }

  const state = activeRun;
  state.status = "running";
  state.slateOptions = null;
  persistRunState(state);
  activeRunPromise = executeRun(state, slateId);

  return { ok: true, run: state };
}

export { STEP_DEFINITIONS };
