import { NextResponse } from "next/server";

import { getTodayChicagoDate } from "@/lib/currentDate";
import { listSlates } from "@/lib/optimizerWorkspace/poolCache";

export const dynamic = "force-dynamic";

/** Every DFS slate the configured provider currently exposes for today
 * (America/Chicago) -- always the current date, never client-supplied,
 * matching the rest of this dashboard's "today" discipline. */
export async function GET() {
  const date = getTodayChicagoDate();
  const result = await listSlates(date);
  return NextResponse.json({ date, ...result });
}
