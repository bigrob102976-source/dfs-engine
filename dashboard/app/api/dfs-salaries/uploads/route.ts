import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { listDraftKingsUploads } from "@/lib/draftKingsUpload";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Lists real DraftKings CSV uploads for a slate date (Milestone 19).
 * Milestone 29: admin-only -- part of the admin Slate Operations surface. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = new URL(request.url).searchParams.get("date");
  if (!date || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "Query param `date` (YYYY-MM-DD) is required." }, { status: 400 });
  }

  const result = await listDraftKingsUploads(date);
  if ("error" in result) {
    return NextResponse.json(result, { status: 502 });
  }
  return NextResponse.json({ uploads: result });
}
