import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { filterSlatesForCurrentViewer } from "@/lib/memberSlateVisibility";
import { listSlates } from "@/lib/optimizerWorkspace/poolCache";

export const dynamic = "force-dynamic";

/** Every DFS slate the configured provider currently exposes for today
 * (America/Chicago) -- always the current date, never client-supplied,
 * matching the rest of this dashboard's "today" discipline. Milestone 29:
 * requires login; a non-admin viewer only ever sees PUBLISHED slates
 * here too (lib/memberSlateVisibility.ts), same rule as every
 * /dashboard/* page's slate list. */
export async function GET() {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayChicagoDate();
  const result = await listSlates(date);
  const slates = await filterSlatesForCurrentViewer(result.slates, date);
  return NextResponse.json({ date, ...result, slates });
}
