import { NextResponse } from "next/server";

import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadPool } from "@/lib/optimizerWorkspace/poolCache";
import { isValidSlateId } from "@/lib/optimizerWorkspace/validateSlateId";

export const dynamic = "force-dynamic";

/** Selects a slate and loads (or rebuilds) its player pool: fetch ->
 * build pool -> project ownership, via the same immutable-artifact
 * Python scripts the one-click refresh pipeline uses. Body:
 * { "slateId": "...", "forceRefresh"?: boolean }. Date is always
 * today's America/Chicago date, never client-supplied. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const slateId = (body as { slateId?: unknown } | null)?.slateId;
  const forceRefresh = Boolean((body as { forceRefresh?: unknown } | null)?.forceRefresh);

  if (!isValidSlateId(slateId)) {
    return NextResponse.json({ error: "\"slateId\" (string) is required." }, { status: 400 });
  }

  const date = getTodayChicagoDate();
  try {
    const pool = await loadPool(date, slateId, forceRefresh);
    return NextResponse.json({ pool });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 502 });
  }
}
