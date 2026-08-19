import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSlateStatus } from "@/lib/db/slateStatus";
import { runSlatePipeline } from "@/lib/slatePipeline";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only "Process Slate": runs the full pipeline (player pool +
 * ownership + Native + AI projections -- see lib/slatePipeline.ts) for
 * ONE DK slate. Milestone 29 background-job readiness: this route does
 * NOT await the pipeline -- it marks the slate PROCESSING, fires the
 * work, and returns 202 immediately, exactly like
 * lib/orchestrator/runner.ts::startRefresh() already does for the
 * full-day refresh. The browser tab can close; the work is Node-process-
 * resident, not request-resident (see that file's docstring for what
 * hosting on a worker/job queue would additionally require). */
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

  // runSlatePipeline() itself flips slate_status to PROCESSING as the
  // very first (synchronous) thing it does, before this handler even
  // returns -- see that function's docstring.
  recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_process_started",
    targetType: "slate", targetId: `${date}:${slateId}`, metadata: { date, slateId, slateLabel: label },
  });

  runSlatePipeline(date, slateId, label)
    .then((result) => {
      recordAuditLog({
        actorUserId: admin.id, actorLabel: admin.email, action: "slate_process_completed",
        targetType: "slate", targetId: `${date}:${slateId}`,
        metadata: { date, slateId, status: result.status, errorCount: result.errors.length },
      });
    })
    .catch((err) => {
      recordAuditLog({
        actorUserId: admin.id, actorLabel: admin.email, action: "slate_process_failed",
        targetType: "slate", targetId: `${date}:${slateId}`,
        metadata: { date, slateId, error: err instanceof Error ? err.message : String(err) },
      });
    });

  return NextResponse.json({ status: "started", date, slateId }, { status: 202 });
}
