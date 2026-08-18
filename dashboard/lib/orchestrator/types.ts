// Types for the one-click "Refresh Today's Slate" orchestration engine
// (Milestone 13). A "run" drives the pregame pipeline end to end by
// invoking the existing Python CLI scripts as subprocesses -- this
// module never reimplements scoring/matching/optimization logic, it
// only sequences and reports on scripts that already exist and are
// already tested.

export type PipelineStepId = "research" | "pitchers" | "batters" | "dfsSalaries" | "playerPool" | "ownership" | "optimizer";

/** Milestone 19: how the DFS salary provider for a run was resolved --
 * mirrors dfs/providers/config.py::get_configured_provider()'s `source`
 * return value exactly (see that module's docstring for the full
 * priority cascade). "explicit" | "automatic_fallback" (pre-M19) no
 * longer exists as an automatic outcome -- mock is never used silently. */
export type ProviderSource = "explicit" | "real_dk_csv" | "csv_import_pool" | "mock_explicit" | "unconfigured";

export type StepStatus = "waiting" | "running" | "ready" | "failed" | "needs_input" | "skipped";

export interface StepResult {
  id: PipelineStepId;
  label: string;
  status: StepStatus;
  startedAt: string | null;
  finishedAt: string | null;
  message: string | null;
  artifactPath: string | null;
  command: string[] | null;
  stdoutTail: string | null;
  stderrTail: string | null;
}

/** The final, dashboard-facing reason a run landed where it did. Mirrors
 * the milestone's explicit list of failure states so the UI can show a
 * distinct, honest message for each rather than a generic "error". */
export type RunOutcome =
  | "ready"
  | "mlb_data_failure"
  | "pitcher_agent_failure"
  | "batter_agent_failure"
  | "dfs_not_connected"
  | "dfs_unavailable"
  | "dfs_auth_failed"
  | "dfs_no_slate"
  | "dfs_invalid_slate_id"
  | "needs_slate_selection"
  | "player_matching_failure"
  | "roster_infeasible"
  | "ownership_failure"
  | "optimizer_infeasible"
  | "unexpected_error"
  | "cancelled";

export interface SlateOption {
  slateId: string;
  slateName: string | null;
  gameCount: number | null;
  startTime: string | null;
  // Milestone 26: the research game_ids this slate resolves to (empty
  // when no Research Package was available to resolve against -- see
  // dfs/providers/models.py::ProviderSlateInfo's own docstring) and the
  // player count the provider reported, so every dashboard page can
  // filter to exactly this slate without a second round trip.
  gameIds: string[];
  playerCount: number | null;
}

/** Minimal shape lib/slateFilters.ts's pure helpers need -- just the
 * `selected` slate, not the full SlateContext (status/isMock/etc. from
 * lib/slateContext.ts) -- so those pure, client-safe helpers don't need
 * to import a server-only module's type. */
export interface SlateContextLike {
  selected: SlateOption | null;
}

export interface RunSummary {
  slateDate: string;
  mlbGames: number | null;
  dfsGames: number | null;
  postedLineups: number | null;
  missingLineups: number | null;
  pitcherCount: number | null;
  hitterCount: number | null;
  salaryCoveragePercent: number | null;
  positionCoveragePercent: number | null;
  dkEntries: number | null;
  matchedToMlb: number | null;
  unmatchedCount: number | null;
  rosterFeasibilityPass: boolean | null;
  ownershipReady: boolean;
  lineupCounts: { projection: number | null; balanced: number | null; leverage: number | null };
  lineupSetPaths: { projection: string | null; balanced: string | null; leverage: string | null };
  providerName: string | null;
  isMock: boolean;
  providerSource: ProviderSource | null;
  selectedSlateId: string | null;
  /** Milestone 19: best-effort refresh of the Big Money Research
   * Adjustment Layer (external_projections/) against whatever baseline
   * exists for this date, run right after Ownership. Not a tracked
   * pipeline step -- a CSV-imported/provider baseline is optional, so
   * "no baseline yet" is a normal, non-failing state (see
   * scripts/run_projection_adjustment.py's "no_baseline"/"no_research"
   * statuses), not a run failure. */
  externalProjectionStatus: "ready" | "no_baseline" | "no_research" | "not_attempted" | "error";
  externalProjectionRecordCount: number | null;
}

export interface ExposureChange {
  name: string;
  beforePercent: number | null;
  afterPercent: number | null;
}

/** A pure diff between this run's summary/artifacts and the previous
 * completed run's -- never re-derives facts, only compares two already-
 * computed snapshots. Fields are null/empty when there's nothing to
 * compare against (e.g. first run of the day). */
export interface ChangeReport {
  previousRunId: string | null;
  previousFinishedAt: string | null;
  newPostedLineupGames: number | null;
  scratches: string[];
  starterChanges: string[];
  salaryChangedCount: number | null;
  projectionChangedCount: number | null;
  ownershipChangedCount: number | null;
  exposureChanges: ExposureChange[];
  notes: string[];
}

export type RunStatus = "running" | "completed" | "failed" | "needs_selection" | "cancelled";

/** Milestone 16: a run is either "full" (the original one-click Refresh
 * Today's Slate button -- every step always re-runs, unconditionally,
 * exactly as before) or "smart" (a missing-data-only refresh -- each
 * step in `requestedSteps`' dependency closure is skipped, not
 * re-invoked, if its artifact is already present). `requestedSteps` is
 * null for a full run (every step is implicitly requested). */
export type RunMode = "full" | "smart";

export interface RunState {
  runId: string;
  slateDate: string;
  status: RunStatus;
  outcome: RunOutcome | null;
  startedAt: string;
  finishedAt: string | null;
  currentStepId: PipelineStepId | null;
  steps: StepResult[];
  slateOptions: SlateOption[] | null;
  summary: RunSummary | null;
  changeReport: ChangeReport | null;
  error: string | null;
  mode: RunMode;
  requestedSteps: PipelineStepId[] | null;
}
