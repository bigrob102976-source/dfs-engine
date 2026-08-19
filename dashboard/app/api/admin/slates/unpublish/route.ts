import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { unpublishSlate } from "@/lib/db/slateStatus";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only Unpublish: immediately removes a slate from every
 * member-facing view (see lib/db/slateStatus.ts::unpublishSlate --
 * clears the published pointer, never deletes the underlying processed
 * artifacts or the publish-history record proving it was once live). */
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

  const ok = unpublishSlate(date, slateId, admin.id);
  if (!ok) {
    return NextResponse.json({ error: "This slate is not currently published." }, { status: 409 });
  }

  recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_unpublished",
    targetType: "slate", targetId: `${date}:${slateId}`, metadata: { date, slateId },
  });

  return NextResponse.json({ status: "unpublished" });
}
