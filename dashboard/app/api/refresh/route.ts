import { NextResponse } from "next/server";

import { getCurrentRun, startRefresh } from "@/lib/orchestrator/runner";

export const dynamic = "force-dynamic";

/** Returns the current (or most recently completed) refresh run, or null
 * if none has ever run in this environment. Polled by the dashboard's
 * RefreshPanel while a run is active. */
export async function GET() {
  return NextResponse.json({ run: getCurrentRun() });
}

/** Starts a new one-click "Refresh Today's Slate" run. Takes no body --
 * the slate date is always resolved server-side from the current
 * America/Chicago date, never supplied by the client, so there is
 * nothing here for browser input to manipulate. Returns 409 if a run is
 * already in progress or paused awaiting a slate selection. */
export async function POST() {
  const result = startRefresh();
  if (!result.accepted) {
    return NextResponse.json({ run: result.run, error: "A refresh is already in progress." }, { status: 409 });
  }
  return NextResponse.json({ run: result.run }, { status: 202 });
}
