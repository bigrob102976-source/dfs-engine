import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { filterSlatesForCurrentViewer } from "@/lib/memberSlateVisibility";
import { listSlates } from "@/lib/optimizerWorkspace/poolCache";
import { resolveSlateDate } from "@/lib/slateDate";

export const dynamic = "force-dynamic";

/** Every DFS slate the configured provider currently exposes for a
 * date. Milestone 31.2C: accepts an optional `?date=YYYY-MM-DD` query
 * param; omitted/empty falls back to today's America/Chicago date
 * exactly as before (fully backward compatible) -- see
 * lib/slateDate.ts. A present-but-invalid date is rejected with 400.
 * Milestone 29: requires login; a non-admin viewer only ever sees
 * PUBLISHED slates here too (lib/memberSlateVisibility.ts), same rule
 * as every /dashboard/* page's slate list. */
export async function GET(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { searchParams } = new URL(request.url);
  const dateResolution = resolveSlateDate(searchParams.get("date"));
  if (!dateResolution.ok) {
    return NextResponse.json({ error: dateResolution.error }, { status: 400 });
  }
  const date = dateResolution.date;

  const result = await listSlates(date);
  const slates = await filterSlatesForCurrentViewer(result.slates, date);
  return NextResponse.json({ date, ...result, slates });
}
