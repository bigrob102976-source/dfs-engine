import { claimNextQueuedJob, completeJob, failJob, updateJobProgress, type FailJobOptions } from "./queue";
import { recordHeartbeat } from "./heartbeat";
import { captureError } from "../errorMonitoring";
import { logger } from "../logger";
import type { JobRow, JobType } from "../db/types";

// Milestone 30: job execution -- the code that actually DOES the work a
// claimed job represents. Kept separate from queue.ts (pure persistence)
// so the same handler logic backs both:
//   - the INLINE path (runQueuedJob called directly from
//     app/api/admin/slates/process/route.ts and .../refresh/route.ts,
//     right where the old fire-and-forget .then()/.catch() used to be --
//     local dev and a genuinely single-instance deployment need no
//     separate worker process for this to work), and
//   - a real OUT-OF-PROCESS poll loop (scripts/run-job-worker.ts), for a
//     hosted deployment where WEB and WORKER are separate services (see
//     DEPLOYMENT.md).

export type JobHandler = (job: JobRow, onProgress: (progress: number, step: string) => void) => Promise<void>;

const HANDLERS: Partial<Record<JobType, JobHandler>> = {};

/** Registers the handler for one job type. lib/jobs/slateJobHandlers.ts
 * calls this for PROCESS_SLATE/REFRESH_SLATE at module load. Kept as
 * runtime registration (not a hardcoded switch here) so this module
 * never needs to import lib/slatePipeline.ts directly -- avoids a
 * circular-import risk between the jobs/ and slatePipeline.ts layers. */
export function registerJobHandler(jobType: JobType, handler: JobHandler): void {
  HANDLERS[jobType] = handler;
}

/** A handler throws TransientJobError specifically to mark a failure as
 * safe to retry (a network blip, a momentarily-locked resource) -- ANY
 * OTHER thrown error defaults to non-retryable. This is a deliberately
 * conservative default: a validation failure, a model error, or a
 * roster-infeasible result would fail identically on every retry, so
 * this codebase never blindly retries a plain Error (this milestone's
 * explicit instruction) -- retryability must be an explicit, positive
 * signal from the handler, not an inferred guess from the worker. */
export class TransientJobError extends Error {}

export interface RunJobResult {
  ran: boolean;
  job: JobRow | null;
  status: "SUCCEEDED" | "FAILED" | "QUEUED" | "NO_JOB" | "NO_HANDLER";
}

/** Claims and runs at most one queued job. Returns immediately with
 * `{ran: false, status: "NO_JOB"}` when the queue is empty -- callers
 * decide whether that's a poll-loop's cue to wait, or (the inline path)
 * simply nothing left to do. */
export async function runOneQueuedJob(workerId: string): Promise<RunJobResult> {
  const job = await claimNextQueuedJob(workerId);
  if (!job) return { ran: false, job: null, status: "NO_JOB" };

  await recordHeartbeat(workerId, { currentJobId: job.id, jobType: job.job_type });

  const handler = HANDLERS[job.job_type];
  if (!handler) {
    await failJob(job.id, {
      errorCode: "NO_HANDLER",
      safeErrorMessage: `No handler is registered for job type "${job.job_type}" yet -- architecture-ready, not yet implemented.`,
      retryable: false,
    });
    return { ran: true, job, status: "NO_HANDLER" };
  }

  const startedAt = Date.now();
  const logFields = { jobId: job.id, slateId: job.slate_id ?? undefined, slateDate: job.slate_date ?? undefined, operation: job.job_type };

  try {
    await handler(job, (progress, step) => void updateJobProgress(job.id, progress, step));
    await completeJob(job.id);
    await recordHeartbeat(workerId, { currentJobId: null });
    logger.info("job succeeded", { ...logFields, durationMs: Date.now() - startedAt, status: "SUCCEEDED" });
    return { ran: true, job, status: "SUCCEEDED" };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const retryable = err instanceof TransientJobError;
    const errorCode = retryable ? "WORKER_TRANSIENT_ERROR" : "WORKER_UNEXPECTED_ERROR";
    const failOptions: FailJobOptions = { errorCode, safeErrorMessage: message, retryable };
    const finalStatus = await failJob(job.id, failOptions);
    await recordHeartbeat(workerId, { currentJobId: null });
    captureError(err, { ...logFields, durationMs: Date.now() - startedAt, status: finalStatus });
    return { ran: true, job, status: finalStatus === "QUEUED" ? "QUEUED" : "FAILED" };
  }
}

/** Best-effort helper for the inline (single-process, no separate
 * worker) path used by the Process/Refresh routes: fire-and-forget, same
 * external behavior as the pre-Milestone-30 `.then()/.catch()` call, but
 * now the work happens through the durable, tracked job queue instead of
 * a bare promise this process could lose track of on restart. */
export function runOneQueuedJobInBackground(workerId = "inline"): void {
  void runOneQueuedJob(workerId).catch(() => {
    // runOneQueuedJob already records the failure on the job row itself
    // (failJob) -- nothing further to do with a rejection here.
  });
}
