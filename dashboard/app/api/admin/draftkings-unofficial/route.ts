import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { loadDkUnofficialExplorerData } from "@/lib/draftKingsUnofficialExplorer";

export const dynamic = "force-dynamic";

/** Milestone 31.2 -- backs the admin DraftKings Development Data
 * Explorer. Every GET here triggers real (though bounded -- see
 * scripts/dk_unofficial_explorer.py) live requests to DraftKings'
 * unofficial endpoints, so this is intentionally a manually-triggered
 * admin page load/refresh, never polled automatically. Admin-only,
 * same as every other /api/admin/* route. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { searchParams } = new URL(request.url);
  const sport = searchParams.get("sport");
  if (!sport) {
    return NextResponse.json({ error: "`sport` query param is required." }, { status: 400 });
  }
  const draftGroupIdRaw = searchParams.get("draftGroupId");
  const gameTypeIdRaw = searchParams.get("gameTypeId");
  const draftGroupId = draftGroupIdRaw ? Number(draftGroupIdRaw) : undefined;
  const gameTypeId = gameTypeIdRaw ? Number(gameTypeIdRaw) : undefined;
  if (draftGroupIdRaw && Number.isNaN(draftGroupId)) {
    return NextResponse.json({ error: "`draftGroupId` must be numeric." }, { status: 400 });
  }

  const result = await loadDkUnofficialExplorerData(sport, draftGroupId, gameTypeId);
  if ("error" in result) {
    return NextResponse.json(result, { status: 502 });
  }
  return NextResponse.json(result);
}
