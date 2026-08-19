import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { archiveSlate } from "@/lib/db/slateStatus";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only Archive: terminal-ish state (see lib/db/slateStatus.ts::
 * archiveSlate -- implicitly unpublishes first if currently published,
 * since a member must never keep seeing an archived slate). */
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
  const { date, slateId } = (body as { date?: unknown; slateId?: unknown }) ?? {};
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD) is required." }, { status: 400 });
  }
  if (typeof slateId !== "string" || !slateId) {
    return NextResponse.json({ error: "`slateId` is required." }, { status: 400 });
  }

  const ok = archiveSlate(date, slateId, admin.id);
  if (!ok) {
    return NextResponse.json({ error: "Unknown slate for this date." }, { status: 404 });
  }

  recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_archived",
    targetType: "slate", targetId: `${date}:${slateId}`, metadata: { date, slateId },
  });

  return NextResponse.json({ status: "archived" });
}
