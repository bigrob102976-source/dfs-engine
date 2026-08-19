import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getMockModeEnabled, setMockModeEnabled } from "@/lib/mockMode";

export const dynamic = "force-dynamic";

/** Milestone 19's Mock Mode toggle -- OFF by default, never enabled
 * automatically. GET reflects current state (used by the admin Settings
 * page -- the site-wide DEV MODE banner reads getMockModeEnabled()
 * directly server-side from app/dashboard/layout.tsx, not through this
 * route); POST is the only way to change it. Milestone 29: admin-only --
 * this toggle is also this project's "explicit dev mode" bypass for the
 * source-provenance production guard (dfs/pool_builder.py's
 * UnsafeSourceProvenanceError), so it must never be member-controllable. */
export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const enabled = await getMockModeEnabled();
  return NextResponse.json({ enabled });
}

export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

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
