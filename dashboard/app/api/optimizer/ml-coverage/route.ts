import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getBigMoneyMlCoverage } from "@/lib/bigMoneyMlOptimizer";
import { isValidSlateId } from "@/lib/optimizerWorkspace/validateSlateId";
import { resolveSlateDate } from "@/lib/slateDate";

export const dynamic = "force-dynamic";

/** Milestone 32.4: the BIG MONEY ML COVERAGE gate shown to ADMIN before
 * an ML optimizer build -- pitchers/hitters/combined generated-vs-
 * eligible counts plus model versions, straight from the persisted
 * shadow-inference snapshots (never recomputed, never triggers
 * generation). ADMIN-only, same as selecting the source itself. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const url = new URL(request.url);
  const slateId = url.searchParams.get("slateId");
  if (slateId !== null && !isValidSlateId(slateId)) {
    return NextResponse.json({ error: "\"slateId\" must be a non-empty string." }, { status: 400 });
  }
  const dateResolution = resolveSlateDate(url.searchParams.get("date"));
  if (!dateResolution.ok) {
    return NextResponse.json({ error: dateResolution.error }, { status: 400 });
  }

  const coverage = getBigMoneyMlCoverage(dateResolution.date, slateId);
  return NextResponse.json({ coverage });
}
