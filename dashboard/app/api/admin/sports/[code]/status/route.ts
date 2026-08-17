import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSport, setSportStatus } from "@/lib/db/sports";
import type { SportStatus } from "@/lib/db/types";

export const dynamic = "force-dynamic";

const VALID_STATUSES: SportStatus[] = ["LIVE", "COMING_SOON"];

export async function PATCH(request: Request, ctx: RouteContext<"/api/admin/sports/[code]/status">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  const { code } = await ctx.params;
  const sport = getSport(code);
  if (!sport) return NextResponse.json({ error: "Unknown sport." }, { status: 404 });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const { status } = (body ?? {}) as { status?: unknown };
  if (typeof status !== "string" || !(VALID_STATUSES as string[]).includes(status)) {
    return NextResponse.json({ error: "status must be LIVE or COMING_SOON." }, { status: 400 });
  }

  setSportStatus(code, status as SportStatus);
  recordAuditLog({
    actorUserId: admin.id,
    actorLabel: admin.email,
    action: "sport_status_changed",
    targetType: "sport",
    targetId: code,
    metadata: { fromStatus: sport.status, toStatus: status },
  });
  return NextResponse.json({ ok: true, sport: getSport(code) });
}
