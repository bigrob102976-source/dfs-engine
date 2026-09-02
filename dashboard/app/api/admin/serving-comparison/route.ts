import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { compareAllServingBackendsForDate, compareServingBackends } from "@/lib/servingBackend/comparison";

export const dynamic = "force-dynamic";

/** M5D/M5E -- ADMIN-only shadow comparison between LEGACY_R2 and
 * CANONICAL_POSTGRES serving for real slate data. Never customer-facing,
 * never touches which backend actually serves a customer request (see
 * lib/servingBackend/config.ts) -- this route is read-only observability
 * for the cutover-preparation gate. Exposes no secret: both backends'
 * results are already customer-facing-safe domain objects.
 *
 * GET /api/admin/serving-comparison?date=YYYY-MM-DD                    -> full parity report (M5E)
 * GET /api/admin/serving-comparison?date=YYYY-MM-DD&slateId=dkunofficial-X -> one slate's comparison (M5D) */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { searchParams } = new URL(request.url);
  const date = searchParams.get("date");
  if (!date) {
    return NextResponse.json({ error: "\"date\" (YYYY-MM-DD) query param is required." }, { status: 400 });
  }
  const slateId = searchParams.get("slateId");

  if (slateId) {
    const comparison = await compareServingBackends(date, slateId);
    return NextResponse.json({ comparison });
  }

  const report = await compareAllServingBackendsForDate(date);
  return NextResponse.json({ report });
}
