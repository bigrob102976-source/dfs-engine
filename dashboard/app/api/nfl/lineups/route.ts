import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { createSavedLineup, listSavedLineups } from "@/lib/db/nflSavedLineups";

export const dynamic = "force-dynamic";

// NFL M14 -- persisted saved lineups for the late-swap / game-day
// workflow (see dashboard/lib/db/migrations/0009_nfl_saved_lineups.sql).
// Scoped per (user, draftGroupId) -- never a shared/global lineup list.
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const { searchParams } = new URL(request.url);
  const draftGroupIdRaw = searchParams.get("draftGroupId");
  const draftGroupId = draftGroupIdRaw ? Number.parseInt(draftGroupIdRaw, 10) : NaN;
  if (!Number.isInteger(draftGroupId) || draftGroupId <= 0) {
    return NextResponse.json({ error: "A valid draftGroupId query parameter is required." }, { status: 400 });
  }

  const rows = await listSavedLineups(user.id, draftGroupId);
  return NextResponse.json({
    lineups: rows.map((r) => ({
      id: r.id, draft_group_id: r.draft_group_id, slate_date: r.slate_date, mode: r.mode,
      stack_config: JSON.parse(r.stack_config_json), slots: JSON.parse(r.slots_json),
      created_at: r.created_at, updated_at: r.updated_at,
    })),
  });
}

interface CreateLineupBody {
  draftGroupId: number;
  slateDate: string;
  mode: string;
  stackConfig: Record<string, unknown>;
  slots: unknown[];
}

export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  let body: CreateLineupBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Malformed JSON body." }, { status: 400 });
  }

  if (!Number.isInteger(body.draftGroupId) || body.draftGroupId <= 0) {
    return NextResponse.json({ error: "A valid draftGroupId is required." }, { status: 400 });
  }
  if (typeof body.slateDate !== "string" || !body.slateDate) {
    return NextResponse.json({ error: "slateDate is required." }, { status: 400 });
  }
  if (!Array.isArray(body.slots) || body.slots.length !== 9) {
    return NextResponse.json({ error: "A saved NFL lineup must have exactly 9 roster slots." }, { status: 400 });
  }

  const row = await createSavedLineup({
    userId: user.id, draftGroupId: body.draftGroupId, slateDate: body.slateDate, mode: body.mode || "roster_feasibility",
    stackConfigJson: JSON.stringify(body.stackConfig ?? {}), slotsJson: JSON.stringify(body.slots),
  });

  return NextResponse.json({
    id: row.id, draft_group_id: row.draft_group_id, slate_date: row.slate_date, mode: row.mode,
    stack_config: JSON.parse(row.stack_config_json), slots: JSON.parse(row.slots_json),
    created_at: row.created_at, updated_at: row.updated_at,
  });
}
