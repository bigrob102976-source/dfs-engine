import crypto from "node:crypto";

import { getExecutor } from "../db/executor";
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
// Milestone 33.1: claimNextQueuedJob() is now genuinely safe under real
// multi-worker Postgres concurrency (see that function's own docstring)
// -- previously a documented, honest limitation of the SQLite-only
// implementation this milestone replaces.

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

export async function getJob(jobId: string): Promise<JobRow | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM jobs WHERE id = ?", [jobId]);
  return row ? rowToJob(row) : null;
}

async function findActiveJob(jobType: JobType, slateDate: string | null, slateId: string | null): Promise<JobRow | null> {
  const db = getExecutor();
  // `IS NOT DISTINCT FROM ?` rather than `IS ?`: Postgres's `IS` operator
  // only accepts a literal NULL/TRUE/FALSE on its right-hand side, never
  // a bound parameter -- `IS NOT DISTINCT FROM` is the portable,
  // null-safe equality both SQLite and Postgres accept with a real
  // parameter (needed here because slate_date/slate_id are legitimately
  // NULL for slate-independent job types).
  const row = await db.get<Record<string, unknown>>(
    "SELECT * FROM jobs WHERE job_type = ? AND slate_date IS NOT DISTINCT FROM ? AND slate_id IS NOT DISTINCT FROM ? " +
      "AND status IN ('QUEUED','RUNNING') ORDER BY created_at DESC LIMIT 1",
    [jobType, slateDate, slateId],
  );
  return row ? rowToJob(row) : null;
}

/** Inserts a new QUEUED job, or returns the already-active one for the
 * same (slate_date, slate_id, job_type) -- see idx_jobs_active_uniqueness
 * in the 0005 migration. Never throws on the duplicate-click case. */
export async function enqueueJob(params: EnqueueJobParams): Promise<EnqueueJobResult> {
  const existing = await findActiveJob(params.jobType, params.slateDate, params.slateId);
  if (existing) return { job: existing, created: false };

  const db = getExecutor();
  const now = new Date().toISOString();
  const id = crypto.randomUUID();
  try {
    await db.run(
      `INSERT INTO jobs (
        id, job_type, slate_date, slate_id, status, created_by, created_at, updated_at,
        progress, attempt_count, max_attempts, payload_json
      ) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?, 0, 0, 3, ?)`,
      [id, params.jobType, params.slateDate, params.slateId, params.createdBy, now, now, params.payload ? JSON.stringify(params.payload) : null],
    );
  } catch (err) {
    // A concurrent enqueue raced us and won the unique index -- return
    // its row instead of surfacing a raw constraint-violation error.
    const raced = await findActiveJob(params.jobType, params.slateDate, params.slateId);
    if (raced) return { job: raced, created: false };
    throw err;
  }
  return { job: (await getJob(id))!, created: true };
}

/** Atomically claims the oldest QUEUED job for a given worker: sets
 * status=RUNNING, started_at, worker_id, increments attempt_count.
 * Returns null when no job is queued.
 *
 * Two genuinely different implementations, because "atomic" means
 * different things on the two backends:
 *
 *   - SQLite: node:sqlite's underlying calls are synchronous, but this
 *     function's own `await db.get(...)` / `await db.run(...)` boundary
 *     is NOT -- two concurrent claimNextQueuedJob() calls from the SAME
 *     Node process (e.g. app/api/admin/slates/discover/route.ts firing
 *     one runOneQueuedJob() per newly-discovered slate, none of them
 *     awaited relative to each other) can both `await db.get(...)` and
 *     see the SAME "next" QUEUED id before either one's `await
 *     db.run(...)` has flipped its status -- a real, previously-latent
 *     race this milestone's bulk discovery feature was the first caller
 *     to actually trigger (proven by
 *     app/api/admin/slates/__tests__/discover.test.ts). The retry loop
 *     below is SQLite's answer to Postgres's `FOR UPDATE SKIP LOCKED`:
 *     a lost race (the UPDATE's WHERE status='QUEUED' guard affected 0
 *     rows) just means some OTHER concurrent call already claimed that
 *     specific row, so retrying re-SELECTs whatever is now the
 *     next-oldest QUEUED job instead of giving up -- each successful
 *     claim strictly shrinks the QUEUED set, so every concurrent caller
 *     eventually claims a distinct row (or correctly finds none left).
 *   - PostgreSQL: a real multi-worker deployment has multiple, genuinely
 *     concurrent connections. A SELECT-then-UPDATE here would let two
 *     workers both select the same "next" job before either updates it.
 *     This uses ONE atomic statement instead --
 *     `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *`
 *     -- so Postgres's own row-locking guarantees only one worker's
 *     UPDATE can ever match that row; the loser's subquery skips it
 *     (SKIP LOCKED) and finds the next-oldest QUEUED job instead (or
 *     none). Proven by tests/db/__tests__/jobQueueConcurrency.test.ts
 *     against a real Postgres server when TEST_DATABASE_URL is set. */
export async function claimNextQueuedJob(workerId: string): Promise<JobRow | null> {
  const db = getExecutor();
  const now = new Date().toISOString();

  if (db.backend === "postgres") {
    const row = await db.get<Record<string, unknown>>(
      `UPDATE jobs SET status = 'RUNNING', started_at = ?, updated_at = ?, worker_id = ?, attempt_count = attempt_count + 1
       WHERE id = (SELECT id FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
       RETURNING *`,
      [now, now, workerId],
    );
    return row ? rowToJob(row) : null;
  }

  const MAX_CLAIM_ATTEMPTS = 10;
  for (let attempt = 0; attempt < MAX_CLAIM_ATTEMPTS; attempt += 1) {
    const next = await db.get<{ id: string }>("SELECT id FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 1");
    if (!next) return null;

    const result = await db.run(
      "UPDATE jobs SET status = 'RUNNING', started_at = ?, updated_at = ?, worker_id = ?, attempt_count = attempt_count + 1 WHERE id = ? AND status = 'QUEUED'",
      [now, now, workerId, next.id],
    );
    if (result.changes > 0) return getJob(next.id);
    // Lost the race for this specific row -- another concurrent claimer
    // in this same process claimed it between our SELECT and UPDATE.
    // Retry against whatever is now the next-oldest QUEUED job.
  }
  return null;
}

export async function updateJobProgress(jobId: string, progress: number, currentStep: string | null): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE jobs SET progress = ?, current_step = ?, updated_at = ? WHERE id = ?", [
    Math.max(0, Math.min(100, Math.round(progress))),
    currentStep,
    new Date().toISOString(),
    jobId,
  ]);
}

export async function completeJob(jobId: string): Promise<void> {
  const db = getExecutor();
  const now = new Date().toISOString();
  await db.run("UPDATE jobs SET status = 'SUCCEEDED', progress = 100, finished_at = ?, updated_at = ? WHERE id = ?", [now, now, jobId]);
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
export async function failJob(jobId: string, options: FailJobOptions): Promise<JobStatus> {
  const db = getExecutor();
  const job = await getJob(jobId);
  if (!job) throw new Error(`No such job: ${jobId}`);
  const now = new Date().toISOString();

  const shouldRetry = options.retryable && job.attempt_count < job.max_attempts;
  const nextStatus: JobStatus = shouldRetry ? "QUEUED" : "FAILED";

  // `CASE WHEN ? = 1 THEN ...` rather than `CASE WHEN ? THEN ...`:
  // Postgres requires a genuine boolean expression in a CASE/WHEN
  // condition and will reject a bare integer parameter (unlike SQLite,
  // which is dynamically typed and accepts either) -- comparing the
  // integer flag to 1 is valid, identical-result boolean syntax on both.
  await db.run(
    "UPDATE jobs SET status = ?, error_code = ?, safe_error_message = ?, finished_at = ?, updated_at = ?, worker_id = CASE WHEN ? = 1 THEN worker_id ELSE NULL END WHERE id = ?",
    [nextStatus, options.errorCode, options.safeErrorMessage, nextStatus === "FAILED" ? now : null, now, shouldRetry ? 1 : 0, jobId],
  );

  return nextStatus;
}

export async function listJobsForSlate(slateDate: string, slateId: string): Promise<JobRow[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM jobs WHERE slate_date = ? AND slate_id = ? ORDER BY created_at DESC", [
    slateDate,
    slateId,
  ]);
  return rows.map(rowToJob);
}

export async function listRecentJobs(limit = 50): Promise<JobRow[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", [limit]);
  return rows.map(rowToJob);
}
