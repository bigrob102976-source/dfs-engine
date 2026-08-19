import crypto from "node:crypto";

import { getDb } from "../db/client";
import type { JobRow, JobStatus, JobType } from "../db/types";

// Milestone 30: durable background-job persistence, backing the `jobs`
// table (lib/db/migrations/0005_production_infrastructure.sql). Replaces
// the bare fire-and-forget `runSlatePipeline(...).then().catch()` calls
// in app/api/admin/slates/process/route.ts and .../refresh/route.ts with
// a tracked row: every Process/Refresh click now has a durable job_id,
// a status queryable independent of this Node process's memory, and
// idempotency enforced at the DB level (idx_jobs_active_uniqueness) so a
// duplicate click can never silently start a second concurrent pipeline
// run for the same slate.
//
// SCOPE NOTE (honest, not silently glossed over): this milestone wires
// PROCESS_SLATE/REFRESH_SLATE end to end -- enqueue, claim, execute
// in-process (lib/jobs/worker.ts's runQueuedJob, called inline from the
// route handlers exactly where the old .then()/.catch() used to be, and
// also callable from a real standalone poll loop -- see
// scripts/run-job-worker.ts). BUILD_LINEUPS/RESULTS_COLLECTION/
// MODEL_EVALUATION are valid job_type values (the CHECK constraint
// already allows them, for forward compatibility) but have no handler
// yet; claiming one throws a clear "not implemented" error rather than
// silently succeeding. A real OUT-OF-PROCESS worker (a separate WORKER
// service actually polling this table over the network, per
// DEPLOYMENT.md's service topology) is architecture-ready but not
// exercised end-to-end in this milestone -- nothing here proves two
// separate Node processes sharing one Postgres `jobs` table in
// production; that is real, separate follow-up validation.

export interface EnqueueJobParams {
  jobType: JobType;
  slateDate: string | null;
  slateId: string | null;
  createdBy: string | null;
  payload?: Record<string, unknown>;
}

export interface EnqueueJobResult {
  job: JobRow;
  /** True if this call created a new QUEUED row. False if an active
   * (QUEUED or RUNNING) job for the same (slate_date, slate_id, job_type)
   * already existed and that existing row was returned instead --
   * idempotency, not an error: a duplicate admin click should not start
   * a second expensive pipeline run. */
  created: boolean;
}

function rowToJob(row: unknown): JobRow {
  return row as JobRow;
}

export function getJob(jobId: string): JobRow | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM jobs WHERE id = ?").get(jobId);
  return row ? rowToJob(row) : null;
}

function findActiveJob(jobType: JobType, slateDate: string | null, slateId: string | null): JobRow | null {
  const db = getDb();
  const row = db
    .prepare(
      "SELECT * FROM jobs WHERE job_type = ? AND slate_date IS ? AND slate_id IS ? AND status IN ('QUEUED','RUNNING') " +
        "ORDER BY created_at DESC LIMIT 1",
    )
    .get(jobType, slateDate, slateId);
  return row ? rowToJob(row) : null;
}

/** Inserts a new QUEUED job, or returns the already-active one for the
 * same (slate_date, slate_id, job_type) -- see idx_jobs_active_uniqueness
 * in the 0005 migration. Never throws on the duplicate-click case. */
export function enqueueJob(params: EnqueueJobParams): EnqueueJobResult {
  const existing = findActiveJob(params.jobType, params.slateDate, params.slateId);
  if (existing) return { job: existing, created: false };

  const db = getDb();
  const now = new Date().toISOString();
  const id = crypto.randomUUID();
  try {
    db.prepare(
      `INSERT INTO jobs (
        id, job_type, slate_date, slate_id, status, created_by, created_at, updated_at,
        progress, attempt_count, max_attempts, payload_json
      ) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?, 0, 0, 3, ?)`,
    ).run(id, params.jobType, params.slateDate, params.slateId, params.createdBy, now, now, params.payload ? JSON.stringify(params.payload) : null);
  } catch (err) {
    // A concurrent enqueue raced us and won the unique index -- return
    // its row instead of surfacing a raw constraint-violation error.
    const raced = findActiveJob(params.jobType, params.slateDate, params.slateId);
    if (raced) return { job: raced, created: false };
    throw err;
  }
  return { job: getJob(id)!, created: true };
}

/** Atomically claims the oldest QUEUED job for a given worker: sets
 * status=RUNNING, started_at, worker_id, increments attempt_count.
 * Returns null when no job is queued. Single-connection node:sqlite
 * means this process never races itself; a real multi-worker Postgres
 * deployment would need this wrapped in a transaction with
 * `FOR UPDATE SKIP LOCKED` or equivalent -- noted in DEPLOYMENT.md as
 * remaining work for genuine multi-worker concurrency. */
export function claimNextQueuedJob(workerId: string): JobRow | null {
  const db = getDb();
  const next = db.prepare("SELECT id FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 1").get() as { id: string } | undefined;
  if (!next) return null;

  const now = new Date().toISOString();
  db.prepare(
    "UPDATE jobs SET status = 'RUNNING', started_at = ?, updated_at = ?, worker_id = ?, attempt_count = attempt_count + 1 WHERE id = ? AND status = 'QUEUED'",
  ).run(now, now, workerId, next.id);

  return getJob(next.id);
}

export function updateJobProgress(jobId: string, progress: number, currentStep: string | null): void {
  const db = getDb();
  db.prepare("UPDATE jobs SET progress = ?, current_step = ?, updated_at = ? WHERE id = ?").run(
    Math.max(0, Math.min(100, Math.round(progress))),
    currentStep,
    new Date().toISOString(),
    jobId,
  );
}

export function completeJob(jobId: string): void {
  const db = getDb();
  const now = new Date().toISOString();
  db.prepare("UPDATE jobs SET status = 'SUCCEEDED', progress = 100, finished_at = ?, updated_at = ? WHERE id = ?").run(now, now, jobId);
}

export interface FailJobOptions {
  errorCode: string;
  safeErrorMessage: string;
  /** Bounded, controlled retry for TRANSIENT failures only -- never for
   * validation/model errors, which will fail identically on every retry.
   * Callers (lib/jobs/worker.ts) decide this per error, not this
   * function -- see that module's RETRYABLE_ERROR_CODES. */
  retryable: boolean;
}

/** Marks a job FAILED, or resets it to QUEUED for another attempt when
 * `retryable` is true and attempt_count hasn't reached max_attempts yet
 * -- bounded retry, never infinite. */
export function failJob(jobId: string, options: FailJobOptions): JobStatus {
  const db = getDb();
  const job = getJob(jobId);
  if (!job) throw new Error(`No such job: ${jobId}`);
  const now = new Date().toISOString();

  const shouldRetry = options.retryable && job.attempt_count < job.max_attempts;
  const nextStatus: JobStatus = shouldRetry ? "QUEUED" : "FAILED";

  db.prepare(
    "UPDATE jobs SET status = ?, error_code = ?, safe_error_message = ?, finished_at = ?, updated_at = ?, worker_id = CASE WHEN ? THEN worker_id ELSE NULL END WHERE id = ?",
  ).run(nextStatus, options.errorCode, options.safeErrorMessage, nextStatus === "FAILED" ? now : null, now, shouldRetry ? 1 : 0, jobId);

  return nextStatus;
}

export function listJobsForSlate(slateDate: string, slateId: string): JobRow[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM jobs WHERE slate_date = ? AND slate_id = ? ORDER BY created_at DESC").all(slateDate, slateId);
  return rows.map(rowToJob);
}

export function listRecentJobs(limit = 50): JobRow[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?").all(limit);
  return rows.map(rowToJob);
}
