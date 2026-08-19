import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSlateStatus } from "@/lib/db/slateStatus";
import { runSlatePipeline } from "@/lib/slatePipeline";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only "Refresh Data": identical underlying pipeline to Process
 * (lib/slatePipeline.ts::runSlatePipeline -- see that module's docstring
 * for why they're the same operation), exposed as its own action/audit
 * label so "the DK salary source was never re-uploaded, only volatile
 * inputs were refreshed" is explicit in the audit trail and process
 * history, per this milestone's "Admin should NOT need to upload it
 * again during the day" requirement. Fire-and-forget, same as Process --
 * see that route's docstring for the background-job-readiness note.
 * A currently PUBLISHED slate's member-visible version is untouched
 * until a subsequent Publish (see lib/db/slateStatus.ts's module
 * docstring -- this is the atomic-member-view guarantee). */
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
  // Note: runSlatePipeline() itself flips slate_status.status to
  // PROCESSING/READY/PARTIAL/ERROR as it runs -- it never touches the
  // published_* pointer columns, so a currently-published slate stays
  // fully member-visible (via getPublishedVersion/listPublishedSlateIds,
  // both gated on published_version alone) for the entire duration of
  // this refresh. See lib/db/slateStatus.ts's docstrings.

  recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_refresh_started",
    targetType: "slate", targetId: `${date}:${slateId}`, metadata: { date, slateId, slateLabel: label },
  });

  runSlatePipeline(date, slateId, label)
    .then((result) => {
      recordAuditLog({
        actorUserId: admin.id, actorLabel: admin.email, action: "slate_refresh_completed",
        targetType: "slate", targetId: `${date}:${slateId}`,
        metadata: { date, slateId, status: result.status, errorCount: result.errors.length },
      });
    })
    .catch((err) => {
      recordAuditLog({
        actorUserId: admin.id, actorLabel: admin.email, action: "slate_refresh_failed",
        targetType: "slate", targetId: `${date}:${slateId}`,
        metadata: { date, slateId, error: err instanceof Error ? err.message : String(err) },
      });
    });

  return NextResponse.json({ status: "started", date, slateId }, { status: 202 });
}
