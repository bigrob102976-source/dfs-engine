import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { listProjectionImports } from "@/lib/csvImport";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Import History table: every CSV-imported baseline snapshot for a
 * slate date, newest first, with which one is currently active.
 * Milestone 29: admin-only. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = new URL(request.url).searchParams.get("date");
  if (!date || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "Query param `date` (YYYY-MM-DD) is required." }, { status: 400 });
  }

  const result = await listProjectionImports(date);
  if ("error" in result) {
    return NextResponse.json(result, { status: 502 });
  }
  return NextResponse.json({ imports: result });
}
