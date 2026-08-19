import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { loadPool } from "@/lib/optimizerWorkspace/poolCache";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Milestone 26: rebuilds ONE slate's player pool + slate-scoped
 * ownership -- the exact same fetch -> build -> ownership pipeline the
 * Optimizer already uses (lib/optimizerWorkspace/poolCache.ts::loadPool),
 * just exposed as its own action from the admin Slate Operations page so
 * an admin can refresh a single slate without opening the Optimizer.
 * Milestone 29: admin-only -- refreshing backend slate data is an admin
 * action; see /api/admin/slates/refresh for the full pipeline (this
 * route stays as the lighter pool-only rebuild the admin UI can also
 * call). */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

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

  try {
    const pool = await loadPool(date, slateId, true);
    return NextResponse.json({ status: "ready", pool });
  } catch (err) {
    return NextResponse.json({ status: "error", error: err instanceof Error ? err.message : String(err) }, { status: 502 });
  }
}
