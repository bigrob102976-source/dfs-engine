import { NextResponse } from "next/server";

import { loadPool } from "@/lib/optimizerWorkspace/poolCache";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Milestone 26: rebuilds ONE slate's player pool + slate-scoped
 * ownership -- the exact same fetch -> build -> ownership pipeline the
 * Optimizer already uses (lib/optimizerWorkspace/poolCache.ts::loadPool),
 * just exposed as its own action from the Slate Manager page so a user
 * can refresh a single slate without opening the Optimizer. */
export async function POST(request: Request) {
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
