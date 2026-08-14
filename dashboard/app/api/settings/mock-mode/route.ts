import { NextResponse } from "next/server";

import { getMockModeEnabled, setMockModeEnabled } from "@/lib/mockMode";

export const dynamic = "force-dynamic";

/** Milestone 19's Mock Mode toggle -- OFF by default, never enabled
 * automatically. GET reflects current state (used by the Settings page
 * and the site-wide DEV MODE banner); POST is the only way to change it
 * (the Settings page's toggle, or the "Enable Mock Mode" button shown
 * when no live DraftKings salary provider is configured). */
export async function GET() {
  const enabled = await getMockModeEnabled();
  return NextResponse.json({ enabled });
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const enabled = (body as { enabled?: unknown })?.enabled;
  if (typeof enabled !== "boolean") {
    return NextResponse.json({ error: "`enabled` must be a boolean." }, { status: 400 });
  }

  const result = await setMockModeEnabled(enabled);
  if ("error" in result) {
    return NextResponse.json(result, { status: 502 });
  }
  return NextResponse.json(result);
}
