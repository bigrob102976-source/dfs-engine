// Milestone 29: the ADMIN-only "Process Slate" / "Refresh Data" pipeline.
// Reuses existing pipeline components verbatim -- never re-implements
// pool building, ownership, or projection math:
//   - lib/optimizerWorkspace/poolCache.ts::loadPool() already runs the
//     real fetch -> build player pool -> project ownership sequence
//     (scripts/fetch_dfs_slate.py, build_dfs_pool_from_provider.py,
//     project_dk_ownership.py).
//   - scripts/run_native_projection_engine.py / run_ai_projection_engine.py
//     are the same CLI entry points Milestone 23/M20 already built --
//     this is the first caller to invoke them from the dashboard rather
//     than manually from a terminal.
// "Process" and "Refresh" are the SAME underlying operation (both just
// re-run this against whatever DK source is currently on disk -- neither
// ever prompts for or requires a new upload); they're exposed as two
// distinct admin actions/labels purely so the audit trail and status
// board read naturally ("Process" the first time, "Refresh" afterward).

import { ARTIFACT_DIRS, artifactPath, toArtifactKey } from "./artifactRoot";
import type { SlateLifecycleStatus } from "./db/types";
import { refreshCanonicalEligibilityForDate, type EligibilityRefreshForDateResult } from "./db/canonicalEligibility";
import { upsertSlateStatus } from "./db/slateStatus";
import { findLatestFile } from "./discovery";
import { loadLatestDkMatchReport, loadLatestDKPlayerPool, loadLatestOwnershipSnapshot } from "./loaders";
import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";
import { loadPool } from "./optimizerWorkspace/poolCache";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { captureSlateState, diffSlateState, type SlateChangeReport } from "./slateChangeReport";
import { evaluatePublishReadiness } from "./slatePublishReadiness";

export interface SlatePipelineResult {
  status: SlateLifecycleStatus; // READY | PARTIAL | ERROR
  errors: string[];
  // M32.7: "After Refresh Data, show what changed" -- a before/after
  // diff of already-persisted state (see lib/slateChangeReport.ts).
  // Never recomputes eligibility/projections itself.
  changeReport: SlateChangeReport;
  // M7A/M7J: observability ONLY -- a canonical-eligibility-refresh
  // problem is NEVER folded into `errors`/`status` above (this is the
  // LEGACY, customer-facing pipeline outcome; canonical Postgres is
  // shadow-only, ADMIN_ONLY -- see lib/servingBackend/config.ts). null
  // when refreshCanonicalEligibilityForDate itself threw unexpectedly
  // (belt-and-suspenders; it's designed never to).
  canonicalEligibilityRefresh: EligibilityRefreshForDateResult | null;
}

async function nativeSnapshotPath(date: string): Promise<string | null> {
  return findLatestFile(artifactPath(ARTIFACT_DIRS.nativeProjectionSnapshots, date), "native_projection_");
}

async function aiSnapshotPath(date: string): Promise<string | null> {
  return findLatestFile(artifactPath(ARTIFACT_DIRS.aiProjectionSnapshots, date), "ai_projection_");
}

async function vegasSnapshotPath(date: string): Promise<string | null> {
  return findLatestFile(artifactPath(ARTIFACT_DIRS.gameEnvironmentSnapshots, date), "environment_");
}

/** Research artifacts (research_output/<date>/games.json etc.) are NOT
 * timestamped/immutable snapshots the way pool/native/AI/ownership are
 * (see research/engine.py) -- there is no single "latest file" version
 * to pin here, only the per-date directory. Recorded as a best-effort
 * reference, not a strict pin. */
function researchSnapshotReference(date: string): string {
  return `${ARTIFACT_DIRS.research}/${date}`;
}

/** Runs the process/refresh pipeline for one slate: rebuilds its player
 * pool + ownership, then (best-effort) refreshes date-level Native and
 * AI projections. Never re-uploads or re-selects a DK source -- always
 * operates on whatever is already on disk. Updates slate_status
 * throughout (PROCESSING while running, then READY/PARTIAL/ERROR) so an
 * admin polling the status board sees live progress. Returns without
 * throwing even on partial failure -- the caller decides what to do with
 * a PARTIAL/ERROR result (e.g. still show it, just don't allow Publish). */
export async function runSlatePipeline(
  date: string,
  slateId: string,
  slateLabel: string | null,
  // Milestone 30: optional, additive -- reports coarse progress against
  // this function's real stages (no fabricated fine-grained "M28
  // performance stages"; none exist -- see lib/jobs/slateJobHandlers.ts).
  // Every existing caller omits this and gets identical behavior to
  // before this parameter existed.
  onProgress: (progress: number, step: string) => void = () => {},
): Promise<SlatePipelineResult> {
  const now = new Date().toISOString();
  // M33.2: the PROCESSING flip is the very first await in this function,
  // deliberately ahead of captureSlateState() below -- app/api/admin/
  // slates/process/route.ts's 409-if-already-processing concurrency guard
  // (and refresh/route.ts's equivalent) depends on this write landing
  // before a near-simultaneous second request's getSlateStatus() read.
  // captureSlateState() now goes through the async StorageBackend (real
  // I/O, potentially several awaits) rather than the synchronous fs reads
  // it used pre-M33.2, so it can no longer be allowed to run first without
  // risking that race -- see this function's own callers' docstrings.
  await upsertSlateStatus(date, slateId, { slateLabel, status: "PROCESSING" });
  // M32.7: captured BEFORE anything else runs -- the "before" half of the
  // Admin Change Report (see lib/slateChangeReport.ts). Cheap, read-only.
  const stateBefore = await captureSlateState(date, slateId);

  const errors: string[] = [];

  // M32.7 AUTOMATIC PROMOTION -- the root fix: refresh
  // research_output/<date>/{games,teams,pitchers,batters}.json from the
  // live MLB schedule/lineups on EVERY run, not just the first. Confirmed
  // live gap this milestone's own validation surfaced:
  // dfs/pool_builder.py::ensure_research_package() only ever calls
  // research/engine.py::build_research_package() when the package is
  // MISSING (ResearchPackageNotFoundError) -- once today's files exist
  // from an early-morning first refresh, they are simply READ forever
  // after, so a newly-POSTED lineup later in the day would never reach
  // any later "Refresh Data" run at all without this step. Safe to
  // re-run any number of times (overwrites cleanly, not an
  // immutable/no-clobber snapshot -- see scripts/build_research_package.py).
  onProgress(1, "Refreshing MLB schedule and lineups");
  const researchResult = await runPythonScript("scripts/build_research_package.py", ["--date", date]);
  if (researchResult.exitCode !== 0) {
    errors.push(`Research package refresh failed: ${tail(researchResult.stdout + researchResult.stderr, 800)}`);
  }

  // M7A -- automatic canonical eligibility refresh, reusing THIS exact
  // research-refresh event (never a second research fetch, never a new
  // scheduler/polling loop -- M7 rules #5/#6). Runs regardless of
  // researchResult's own exit code: scripts/compute_canonical_eligibility.py
  // honestly reports NO_RESEARCH_PACKAGE if nothing usable exists, rather
  // than needing this call site to special-case that. Deliberately
  // isolated from `errors`/`status` above -- canonical Postgres is
  // shadow-only/ADMIN_ONLY, so a canonical-side problem must NEVER make
  // this LEGACY, customer-facing pipeline look like it failed (M7A/M7J).
  // Logged for visibility (M7K), never thrown.
  let canonicalEligibilityRefresh: EligibilityRefreshForDateResult | null = null;
  try {
    canonicalEligibilityRefresh = await refreshCanonicalEligibilityForDate(date);
    if (canonicalEligibilityRefresh.slatesFailed > 0) {
      console.error(
        `[M7A] canonical eligibility refresh for ${date}: ${canonicalEligibilityRefresh.slatesFailed}/${canonicalEligibilityRefresh.slatesFound} slate(s) failed`,
        canonicalEligibilityRefresh.perSlate.filter((s) => s.status !== "OK"),
      );
    }
  } catch (err) {
    console.error(`[M7A] canonical eligibility refresh for ${date} threw unexpectedly (isolated -- legacy pipeline unaffected):`, err);
  }

  // M8B/M8D -- refreshes the roster-derived identity crosswalk
  // (player_identity/refresh.py), consulted by BOTH legacy's
  // dfs/player_resolver.py (widening its candidate pool beyond today's
  // probable-pitcher/posted-lineup research) and canonical's
  // canonical_ingestion/identity_bridge.py. MOVED here (was previously
  // after "Building player pool" below) once a live M8 audit found its
  // ONLY real dependency is research_output/<date>/teams.json --
  // written by "Refreshing MLB schedule and lineups" just above, NOT by
  // the DK-dependent pool-build step below. The prior placement meant a
  // DK-side failure in the pool-build step's own try/catch (which
  // returns early -- see below) silently prevented this crosswalk from
  // ever refreshing at all, even though it has nothing to do with DK.
  // Live-confirmed root cause of a real 9-day-stale crosswalk that made
  // canonical unable to resolve a player (Davis Martin, MLBAM 663436)
  // that legacy resolved fine from its own independent, always-current
  // probable-starters research file. Never blocks the slate:
  // scripts/refresh_player_identity.py always exits 0 and a missing/
  // failed team fetch is recorded in its own JSON status line, not as a
  // pipeline failure -- `status` below is computed from readiness/pool
  // presence alone, never from `errors.length`.
  onProgress(2, "Refreshing MLB player identity");
  const identityResult = await runPythonScript("scripts/refresh_player_identity.py", ["--date", date]);
  if (identityResult.exitCode !== 0) {
    errors.push(`Player identity refresh failed: ${tail(identityResult.stdout + identityResult.stderr, 800)}`);
  }

  // M32.7 AUTOMATIC PROMOTION: re-score the Pitcher/Batter Agents FIRST,
  // before the player pool is (re)built below -- confirmed live gap
  // this milestone's own validation surfaced: "Building player pool"
  // only ever READS whichever predictions/*_board_*.json snapshot
  // already happens to exist (dfs/pool_builder.py::load_snapshot_arg),
  // it never triggers agent scoring itself. Without this step, a newly-
  // posted lineup's hitters get identity-resolved and eligibility-
  // promoted correctly, but the pool's own Independent projection (and
  // therefore Ownership, which reads that same field) stays stale/null
  // for them until someone happens to re-run the agents by hand. Never
  // blocks the slate: both scripts fail loudly (non-zero exit) only on
  // a genuine crash, never for "no eligible players yet" (an early
  // slate with nobody confirmed yet still exits 0 with zero scored).
  onProgress(3, "Scoring starting pitchers");
  const pitcherAgentResult = await runPythonScript("scripts/run_real_pitcher_agent.py", ["--date", date]);
  if (pitcherAgentResult.exitCode !== 0) {
    errors.push(`Pitcher Agent scoring failed: ${tail(pitcherAgentResult.stdout + pitcherAgentResult.stderr, 800)}`);
  }

  onProgress(4, "Scoring confirmed starting hitters");
  const batterAgentResult = await runPythonScript("scripts/run_real_batter_agent.py", ["--date", date]);
  if (batterAgentResult.exitCode !== 0) {
    errors.push(`Batter Agent scoring failed: ${tail(batterAgentResult.stdout + batterAgentResult.stderr, 800)}`);
  }

  onProgress(5, "Building player pool");

  try {
    await loadPool(date, slateId, true);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // Milestone 31.1: loadPool() can throw AFTER the pool/match report
    // were already written to disk (e.g. a later read-back step
    // failing) -- in that case the provenance/source hash it computed
    // are real and observable, not "nothing happened." Best-effort
    // recovery only: if nothing was ever written (the common case --
    // e.g. a malformed CSV never got past parsing), these stay null,
    // which is the honest state for a slate that's never built.
    const [recoveredMatchReport, recoveredPool] = await Promise.all([
      loadLatestDkMatchReport(date, slateId),
      loadLatestDKPlayerPool(date, slateId),
    ]);
    const recoveredHash = (recoveredPool.data?.players.find((p) => p.source_sha256)?.source_sha256 as string | undefined) ?? null;
    const recoveredProvenance =
      typeof recoveredMatchReport.data?.source_provenance === "string" ? (recoveredMatchReport.data.source_provenance as string) : null;
    await upsertSlateStatus(date, slateId, {
      status: "ERROR",
      lastProcessedAt: now,
      // M33.2: pinned artifact references are portable, artifact-root-
      // relative object keys (never an admin-machine-local absolute
      // path) -- see the same fix on the READY/PARTIAL path below.
      poolPath: recoveredPool.path ? toArtifactKey(recoveredPool.path) : null,
      matchReportPath: recoveredMatchReport.path ? toArtifactKey(recoveredMatchReport.path) : null,
      sourceHash: recoveredHash,
      sourceProvenance: recoveredProvenance,
    });
    // Nothing progressed -- an honest self-diff (no change) rather than
    // comparing against a state the pipeline never actually reached.
    errors.push(`Player pool build failed: ${message}`);
    return { status: "ERROR", errors, changeReport: diffSlateState(stateBefore, stateBefore), canonicalEligibilityRefresh };
  }

  // M32.7 GLOBAL REFRESH: "Admin Refresh Data should be the single
  // action that advances the day's slate... automatically handle...
  // Vegas, weather..." -- previously ONLY available via the separate
  // /api/game-environment/generate admin action (still there, unchanged,
  // for an admin who wants to refresh weather/Vegas alone without
  // re-running the rest). Added here so a member never has to wonder
  // whether "Refresh Data" covers it. Same non-blocking contract as
  // every other step: scripts/build_game_environment_report.py always
  // exits 0 and reports "no_research" (no research package yet) via its
  // own JSON status line, never a pipeline failure.
  onProgress(37, "Refreshing Vegas/weather/park environment");
  const environmentResult = await runPythonScript("scripts/build_game_environment_report.py", ["--date", date]);
  if (environmentResult.exitCode !== 0) {
    errors.push(`Game environment refresh failed: ${tail(environmentResult.stdout + environmentResult.stderr, 800)}`);
  }

  onProgress(40, "Running Native projection engine");
  const nativeResult = await runPythonScript("scripts/run_native_projection_engine.py", ["--date", date]);
  if (nativeResult.exitCode !== 0) {
    errors.push(`Native projection engine failed: ${tail(nativeResult.stdout + nativeResult.stderr, 800)}`);
  }

  onProgress(70, "Running AI projection engine");
  const aiResult = await runPythonScript("scripts/run_ai_projection_engine.py", ["--date", date]);
  if (aiResult.exitCode !== 0) {
    errors.push(`AI projection engine failed: ${tail(aiResult.stdout + aiResult.stderr, 800)}`);
  }

  // FantasyPros (optional, test/evaluation comparison source -- never
  // affects `status` below, which is computed from readiness/pool
  // presence alone). Unlike native/AI, this script always exits 0 for
  // every EXPECTED outcome (not configured, no research yet, API error)
  // -- it prints a JSON status line instead, since "FantasyPros isn't
  // configured" is normal, not a pipeline failure. Only a genuinely
  // unexpected non-zero exit is recorded as an error here.
  onProgress(85, "Fetching FantasyPros projections");
  const fantasyProsResult = await runPythonScript("scripts/fetch_fantasypros_projections.py", ["--date", date]);
  const fantasyProsStatus = parseLastJsonLine(fantasyProsResult.stdout)?.status;
  if (fantasyProsResult.exitCode !== 0) {
    errors.push(`FantasyPros fetch failed: ${tail(fantasyProsResult.stdout + fantasyProsResult.stderr, 800)}`);
  } else if (fantasyProsStatus === "api_error") {
    errors.push(`FantasyPros API error: ${tail(fantasyProsResult.stdout, 400)}`);
  }

  // BlueCollar DFS (optional, ADMIN-testable comparison/optimizer
  // source -- never affects `status` below). Same non-blocking contract
  // as FantasyPros above: scripts/fetch_bluecollar_projections.py
  // always exits 0 for every EXPECTED outcome (not configured, no
  // research yet, slate match ambiguous/failed, API error) and reports
  // status via a trailing JSON line -- BlueCollar being down or
  // unmatched must never fail the whole slate refresh. This is the
  // ONLY place BlueCollar's API is ever called from -- a member's page
  // load only ever reads the snapshot this step persists (see
  // lib/blueCollarProjections.ts), never re-fetches.
  onProgress(87, "Fetching BlueCollar DFS projections");
  const blueCollarResult = await runPythonScript("scripts/fetch_bluecollar_projections.py", ["--date", date, "--slate-id", slateId]);
  const blueCollarStatus = parseLastJsonLine(blueCollarResult.stdout)?.status;
  if (blueCollarResult.exitCode !== 0) {
    errors.push(`BlueCollar fetch failed: ${tail(blueCollarResult.stdout + blueCollarResult.stderr, 800)}`);
  } else if (blueCollarStatus === "api_error") {
    errors.push(`BlueCollar API error: ${tail(blueCollarResult.stdout, 400)}`);
  } else if (blueCollarStatus === "slate_match_failed") {
    errors.push(`BlueCollar not updated: ${tail(blueCollarResult.stdout, 400)}`);
  }

  // Milestone 32.2B: Big Money ML -- SHADOW MODE, experimental. Same
  // non-blocking contract as FantasyPros above: this script always
  // exits 0 for every EXPECTED outcome (no eligible starters, feature
  // parity insufficient, model artifact missing) and reports status via
  // a trailing JSON line. A shadow-model failure must never make an
  // entire slate unpublishable -- `status` below is still computed from
  // readiness/pool presence alone, never from this step.
  onProgress(90, "Running Big Money ML shadow inference (pitchers)");
  const mlShadowResult = await runPythonScript("scripts/run_ml_shadow_inference.py", ["--date", date]);
  const mlShadowStatus = parseLastJsonLine(mlShadowResult.stdout)?.status;
  if (mlShadowResult.exitCode !== 0) {
    errors.push(`Big Money ML shadow inference failed: ${tail(mlShadowResult.stdout + mlShadowResult.stderr, 800)}`);
  } else if (mlShadowStatus === "error" || mlShadowStatus === "feature_parity_error") {
    errors.push(`Big Money ML shadow inference: ${mlShadowStatus} -- ${tail(mlShadowResult.stdout, 400)}`);
  }

  // Milestone 32.3B: hitter side of the same shadow inference, run
  // AFTER identity/eligibility/lineup confirmation (pool build already
  // happened above) and before final admin status display. Same
  // non-blocking contract as the pitcher step above -- a shadow-model
  // failure must never make an entire slate unpublishable.
  onProgress(92, "Running Big Money ML shadow inference (hitters)");
  const mlHitterShadowResult = await runPythonScript("scripts/run_ml_hitter_shadow_inference.py", ["--date", date]);
  const mlHitterShadowStatus = parseLastJsonLine(mlHitterShadowResult.stdout)?.status;
  if (mlHitterShadowResult.exitCode !== 0) {
    errors.push(`Big Money ML hitter shadow inference failed: ${tail(mlHitterShadowResult.stdout + mlHitterShadowResult.stderr, 800)}`);
  } else if (mlHitterShadowStatus === "error" || mlHitterShadowStatus === "feature_parity_error") {
    errors.push(`Big Money ML hitter shadow inference: ${mlHitterShadowStatus} -- ${tail(mlHitterShadowResult.stdout, 400)}`);
  }

  onProgress(95, "Finalizing slate status");

  const [pool, matchReport, ownership, nativePath, aiPath, vegasPath, readiness, stateAfter] = await Promise.all([
    loadLatestDKPlayerPool(date, slateId),
    loadLatestDkMatchReport(date, slateId),
    loadLatestOwnershipSnapshot(date, slateId),
    nativeSnapshotPath(date),
    aiSnapshotPath(date),
    vegasSnapshotPath(date),
    evaluatePublishReadiness(date, slateId),
    captureSlateState(date, slateId),
  ]);
  // Milestone 27.4 stamps source_sha256 per-player (dfs/models.py::DFSPlayer),
  // not once at the top of the match report -- every row from one CSV
  // shares the same hash, so the first player's is the slate's own hash.
  const sourceHash = (pool.data?.players.find((p) => p.source_sha256)?.source_sha256 as string | undefined) ?? null;
  const sourceProvenance =
    typeof matchReport.data?.source_provenance === "string" ? (matchReport.data.source_provenance as string) : null;

  const status: SlateLifecycleStatus = readiness.ok ? "READY" : pool.data ? "PARTIAL" : "ERROR";
  const changeReport = diffSlateState(stateBefore, stateAfter);

  // M33.2: `poolPath`/`matchReportPath`/`ownershipPath`/`nativeSnapshotPath`/
  // `aiSnapshotPath`/`vegasSnapshotPath` are persisted into the slate_status
  // table (and copied into slate_publish_history on Publish -- see
  // lib/db/slateStatus.ts) as portable, artifact-root-relative object keys
  // via toArtifactKey(), never the admin-machine-local absolute filesystem
  // path artifactPath()/findLatestFile() return -- a hosted deployment can
  // have the admin's pipeline-processing machine and a member's read-
  // serving machine be different hosts, so an absolute local path stored
  // here would be meaningless to whichever machine reads it back.
  // researchSnapshotPath is already a relative reference (see
  // researchSnapshotReference() above), so it's left unwrapped.
  await upsertSlateStatus(date, slateId, {
    slateLabel,
    status,
    poolPath: pool.path ? toArtifactKey(pool.path) : null,
    matchReportPath: matchReport.path ? toArtifactKey(matchReport.path) : null,
    ownershipPath: ownership.path ? toArtifactKey(ownership.path) : null,
    nativeSnapshotPath: nativePath ? toArtifactKey(nativePath) : null,
    aiSnapshotPath: aiPath ? toArtifactKey(aiPath) : null,
    vegasSnapshotPath: vegasPath ? toArtifactKey(vegasPath) : null,
    researchSnapshotPath: researchSnapshotReference(date),
    sourceHash,
    sourceProvenance,
    validationJson: JSON.stringify(readiness),
    changeReportJson: JSON.stringify(changeReport),
    lastProcessedAt: now,
    lastRefreshedAt: now,
  });

  return { status, errors, changeReport, canonicalEligibilityRefresh };
}
