import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { deleteSavedLineup, getSavedLineupById } from "@/lib/db/nflSavedLineups";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, ctx: RouteContext<"/api/nfl/lineups/[id]">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const { id } = await ctx.params;
  const row = await getSavedLineupById(id);
  if (!row || row.user_id !== user.id) {
    return NextResponse.json({ error: "Saved lineup not found." }, { status: 404 });
  }

  return NextResponse.json({
    id: row.id, draft_group_id: row.draft_group_id, slate_date: row.slate_date, mode: row.mode,
    stack_config: JSON.parse(row.stack_config_json), slots: JSON.parse(row.slots_json),
    created_at: row.created_at, updated_at: row.updated_at,
  });
}

export async function DELETE(_request: Request, ctx: RouteContext<"/api/nfl/lineups/[id]">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const { id } = await ctx.params;
  const deleted = await deleteSavedLineup(id, user.id);
  if (!deleted) {
    return NextResponse.json({ error: "Saved lineup not found." }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}
