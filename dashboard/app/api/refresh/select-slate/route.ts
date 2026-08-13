import { NextResponse } from "next/server";

import { resumeWithSlateSelection } from "@/lib/orchestrator/runner";

export const dynamic = "force-dynamic";

/** Resumes a paused run that's awaiting a DFS slate choice (the provider
 * exposed more than one). Body: { "slateId": "..." }. The slateId is
 * browser-supplied but is validated against the run's own already-
 * discovered slate options before it's ever passed to a Python
 * subprocess -- arbitrary client strings never reach the command line. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const slateId = (body as { slateId?: unknown } | null)?.slateId;
  if (typeof slateId !== "string" || slateId.length === 0) {
    return NextResponse.json({ error: "\"slateId\" (string) is required." }, { status: 400 });
  }

  const result = resumeWithSlateSelection(slateId);
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 409 });
  }
  return NextResponse.json({ run: result.run }, { status: 202 });
}
