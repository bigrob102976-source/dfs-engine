import { NextResponse } from "next/server";

import { activateProjectionImport } from "@/lib/csvImport";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Makes an older CSV-imported baseline snapshot the active one again
 * (a fresh, newer-timestamped copy -- immutable snapshots are never
 * edited in place) and re-runs the adjustment layer so the Optimizer's
 * External/Adjusted projection sources immediately reflect it. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const path = (body as { path?: unknown })?.path;
  const date = (body as { date?: unknown })?.date;
  if (typeof path !== "string" || !path) {
    return NextResponse.json({ error: "`path` is required." }, { status: 400 });
  }
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD) is required." }, { status: 400 });
  }

  const result = await activateProjectionImport(path, date);
  if ("error" in result) {
    return NextResponse.json(result, { status: 400 });
  }
  return NextResponse.json(result);
}
