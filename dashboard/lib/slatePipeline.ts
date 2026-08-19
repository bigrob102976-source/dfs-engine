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

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import type { SlateLifecycleStatus } from "./db/types";
import { upsertSlateStatus } from "./db/slateStatus";
import { findLatestFile } from "./discovery";
import { loadLatestDkMatchReport, loadLatestDKPlayerPool, loadLatestOwnershipSnapshot } from "./loaders";
import { loadPool } from "./optimizerWorkspace/poolCache";
import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { evaluatePublishReadiness } from "./slatePublishReadiness";

export interface SlatePipelineResult {
  status: SlateLifecycleStatus; // READY | PARTIAL | ERROR
  errors: string[];
}

function nativeSnapshotPath(date: string): string | null {
  return findLatestFile(artifactPath(ARTIFACT_DIRS.nativeProjectionSnapshots, date), "native_projection_");
}

function aiSnapshotPath(date: string): string | null {
  return findLatestFile(artifactPath(ARTIFACT_DIRS.aiProjectionSnapshots, date), "ai_projection_");
}

function vegasSnapshotPath(date: string): string | null {
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
export async function runSlatePipeline(date: string, slateId: string, slateLabel: string | null): Promise<SlatePipelineResult> {
  const now = new Date().toISOString();
  upsertSlateStatus(date, slateId, { slateLabel, status: "PROCESSING" });

  try {
    await loadPool(date, slateId, true);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    upsertSlateStatus(date, slateId, { status: "ERROR", lastProcessedAt: now });
    return { status: "ERROR", errors: [`Player pool build failed: ${message}`] };
  }

  const errors: string[] = [];

  const nativeResult = await runPythonScript("scripts/run_native_projection_engine.py", ["--date", date]);
  if (nativeResult.exitCode !== 0) {
    errors.push(`Native projection engine failed: ${tail(nativeResult.stdout + nativeResult.stderr, 800)}`);
  }

  const aiResult = await runPythonScript("scripts/run_ai_projection_engine.py", ["--date", date]);
  if (aiResult.exitCode !== 0) {
    errors.push(`AI projection engine failed: ${tail(aiResult.stdout + aiResult.stderr, 800)}`);
  }

  const pool = loadLatestDKPlayerPool(date, slateId);
  const matchReport = loadLatestDkMatchReport(date, slateId);
  const ownership = loadLatestOwnershipSnapshot(date, slateId);
  // Milestone 27.4 stamps source_sha256 per-player (dfs/models.py::DFSPlayer),
  // not once at the top of the match report -- every row from one CSV
  // shares the same hash, so the first player's is the slate's own hash.
  const sourceHash = (pool.data?.players.find((p) => p.source_sha256)?.source_sha256 as string | undefined) ?? null;
  const sourceProvenance =
    typeof matchReport.data?.source_provenance === "string" ? (matchReport.data.source_provenance as string) : null;

  const readiness = evaluatePublishReadiness(date, slateId);
  const status: SlateLifecycleStatus = readiness.ok ? "READY" : pool.data ? "PARTIAL" : "ERROR";

  upsertSlateStatus(date, slateId, {
    slateLabel,
    status,
    poolPath: pool.path,
    matchReportPath: matchReport.path,
    ownershipPath: ownership.path,
    nativeSnapshotPath: nativeSnapshotPath(date),
    aiSnapshotPath: aiSnapshotPath(date),
    vegasSnapshotPath: vegasSnapshotPath(date),
    researchSnapshotPath: researchSnapshotReference(date),
    sourceHash,
    sourceProvenance,
    validationJson: JSON.stringify(readiness),
    lastProcessedAt: now,
    lastRefreshedAt: now,
  });

  return { status, errors };
}
