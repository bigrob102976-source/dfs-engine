import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSlateStatus } from "@/lib/db/slateStatus";
import { enqueueJob } from "@/lib/jobs/queue";
import { ensureSlateJobHandlersRegistered } from "@/lib/jobs/slateJobHandlers";
import { runOneQueuedJob } from "@/lib/jobs/worker";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only "Process Slate": runs the full pipeline (player pool +
 * ownership + Native + AI projections -- see lib/slatePipeline.ts) for
 * ONE DK slate. Milestone 30: enqueues a durable PROCESS_SLATE job (the
 * `jobs` table -- lib/jobs/queue.ts) instead of a bare fire-and-forget
 * promise, then runs it inline via lib/jobs/worker.ts::runOneQueuedJob so
 * local dev and a single-instance deployment need no separate worker
 * process. This route still does NOT await the pipeline itself -- it
 * enqueues, kicks off execution, and returns 202 immediately; the
 * browser tab can close. A real out-of-process worker (scripts/run-job-
 * worker.ts) can claim the SAME queued row instead once one is actually
 * running -- see that script's docstring for what a hosted multi-service
 * deployment additionally requires. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const { date, slateId, slateLabel } = (body as { date?: unknown; slateId?: unknown; slateLabel?: unknown }) ?? {};
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD) is required." }, { status: 400 });
  }
  if (typeof slateId !== "string" || !slateId) {
    return NextResponse.json({ error: "`slateId` is required." }, { status: 400 });
  }
  const label = typeof slateLabel === "string" ? slateLabel : null;

  const existing = getSlateStatus(date, slateId);
  if (existing?.status === "PROCESSING") {
    return NextResponse.json({ error: "This slate is already processing." }, { status: 409 });
  }

  ensureSlateJobHandlersRegistered();
  const { job } = enqueueJob({ jobType: "PROCESS_SLATE", slateDate: date, slateId, createdBy: admin.id, payload: { slateLabel: label } });

  // The job's own handler (lib/slatePipeline.ts::runSlatePipeline) flips
  // slate_status to PROCESSING as the very first (synchronous) thing it
  // does, before this handler even returns -- see that function's
  // docstring and lib/jobs/worker.ts's claim-then-run-synchronously-up-
  // to-its-first-real-await behavior.
  recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_process_started",
    targetType: "slate", targetId: `${date}:${slateId}`, metadata: { date, slateId, slateLabel: label, jobId: job.id },
  });

  runOneQueuedJob(`inline-${job.id}`).then((result) => {
    const failed = result.status === "FAILED" || result.status === "NO_HANDLER";
    recordAuditLog({
      actorUserId: admin.id, actorLabel: admin.email,
      action: failed ? "slate_process_failed" : "slate_process_completed",
      targetType: "slate", targetId: `${date}:${slateId}`,
      metadata: failed
        ? { date, slateId, jobId: job.id, error: result.job?.safe_error_message ?? null }
        : { date, slateId, jobId: job.id, status: getSlateStatus(date, slateId)?.status ?? null },
    });
  });

  return NextResponse.json({ status: "started", date, slateId, jobId: job.id }, { status: 202 });
}
