import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { listPublishHistory } from "@/lib/db/slateStatus";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only: the full, append-only publish-version history for one
 * slate (lib/db/slateStatus.ts::listPublishHistory) -- every PUBLISHED/
 * UNPUBLISHED/ARCHIVED event ever recorded for it, newest first. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { searchParams } = new URL(request.url);
  const date = searchParams.get("date") ?? "";
  const slateId = searchParams.get("slateId") ?? "";
  if (!DATE_RE.test(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD) query param is required." }, { status: 400 });
  }
  if (!slateId) {
    return NextResponse.json({ error: "`slateId` query param is required." }, { status: 400 });
  }

  return NextResponse.json({ date, slateId, history: listPublishHistory(date, slateId) });
}
