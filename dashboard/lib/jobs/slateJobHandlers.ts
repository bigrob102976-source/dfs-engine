import { runSlatePipeline } from "../slatePipeline";
import { runRefresh } from "../canonicalRefresh";
import { registerJobHandler, type JobHandler } from "./worker";

// Milestone 30: registers the PROCESS_SLATE/REFRESH_SLATE job handlers.
// "Process" and "Refresh" are the same underlying pipeline (see
// lib/slatePipeline.ts's module docstring) -- one handler backs both job
// types. Imported once for its side effect (the registerJobHandler calls
// below) by both the route handlers and scripts/run-job-worker.ts, so
// whichever one runs first registers it exactly the same way.

let registered = false;

export function ensureSlateJobHandlersRegistered(): void {
  if (registered) return;
  registered = true;

  const handler: JobHandler = async (job, onProgress) => {
    const payload = job.payload_json ? (JSON.parse(job.payload_json) as { slateLabel?: string | null }) : {};
    if (!job.slate_date || !job.slate_id) {
      throw new Error(`${job.job_type} job ${job.id} is missing slate_date/slate_id.`);
    }
    const result = await runSlatePipeline(job.slate_date, job.slate_id, payload.slateLabel ?? null, onProgress);
    if (result.status === "ERROR") {
      throw new Error(result.errors.join("; ") || "Slate pipeline reported ERROR with no detail.");
    }
    // PARTIAL is not thrown -- it's a legitimate, already-recorded
    // outcome (see runSlatePipeline's docstring: the caller decides what
    // to do with a partial result). The job still SUCCEEDS; slate_status
    // itself carries the PARTIAL detail for the Slate Operations UI.
  };

  registerJobHandler("PROCESS_SLATE", handler);
  registerJobHandler("REFRESH_SLATE", handler);

  // BREAK-GLASS ADMIN CSV UPLOAD Phase 7: date-level (not slate-level --
  // job.slate_id is deliberately null for this job type, see
  // dashboard/lib/jobs/queue.ts's own support for a null slateId), runs
  // the SAME research/identity/eligibility/Native-projection/ownership
  // sequence the automatic path already runs after every real DK fetch
  // (lib/canonicalRefresh.ts::runRefresh, reused unmodified) so a newly
  // imported admin CSV slate gets real downstream data without any
  // separate, divergent code path.
  const refreshCanonicalDateHandler: JobHandler = async (job) => {
    if (!job.slate_date) {
      throw new Error(`${job.job_type} job ${job.id} is missing slate_date.`);
    }
    const payload = job.payload_json ? (JSON.parse(job.payload_json) as { sport?: string }) : {};
    await runRefresh(job.slate_date, payload.sport ?? "MLB");
    // runRefresh() never throws -- every step is independently isolated
    // and its own failure is captured in the returned summary rather
    // than surfaced here. The job always SUCCEEDS once genuinely
    // attempted; a partial/degraded summary is not a job failure, same
    // as the CLI wrapper's own "always exits 0" contract.
  };
  registerJobHandler("REFRESH_CANONICAL_DATE", refreshCanonicalDateHandler);
}
