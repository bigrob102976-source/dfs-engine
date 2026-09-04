import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { deactivateAdminCsvSlate } from "@/lib/adminCsvImport";
import { recordAuditLog } from "@/lib/db/auditLog";

export const dynamic = "force-dynamic";

/** BREAK-GLASS ADMIN CSV UPLOAD Phase 9: removes an admin-CSV slate
 * from serving (flips validationState to REJECTED -- see
 * lib/adminCsvImport.ts::deactivateAdminCsvSlate's own docstring for why
 * that's the existing, non-destructive mechanism, not a delete). Guarded
 * server-side (both here and in that function, `provider = 'draftkings_csv'`)
 * so this can never be used to pull a real automatic slate. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, reason: "Request body must be JSON." }, { status: 400 });
  }
  const { internalSlateId } = (body as { internalSlateId?: unknown }) ?? {};
  if (typeof internalSlateId !== "string" || !internalSlateId) {
    return NextResponse.json({ ok: false, reason: "`internalSlateId` is required." }, { status: 400 });
  }

  const result = await deactivateAdminCsvSlate(internalSlateId);
  if (!result.ok) {
    return NextResponse.json(result, { status: 404 });
  }

  await recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "admin_csv_slate_deactivated",
    targetType: "slate", targetId: internalSlateId, metadata: { internalSlateId },
  });

  return NextResponse.json(result, { status: 200 });
}
