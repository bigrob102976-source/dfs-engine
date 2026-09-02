import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTomorrowPrefetchSummary, listIdentityReviewQueue, listShadowSlateStatuses } from "@/lib/db/canonicalShadowStatus";

export const dynamic = "force-dynamic";

/** M3J -- admin-only, read-only observability over the canonical shadow
 * ingestion pipeline (M2/M3). ADMIN-only (requireAdminApi() -- a MEMBER
 * gets 403, see this route's own access-control test). Returns ONLY
 * `slates`/`identity_review_queue` row data -- never a database
 * connection string, Railway variable, API key, or storage credential;
 * none of those are ever read by lib/db/canonicalShadowStatus.ts in the
 * first place, so there is nothing here that could leak them. */
export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const [slates, reviewQueue, tomorrowPrefetch] = await Promise.all([
    listShadowSlateStatuses(),
    listIdentityReviewQueue("PENDING"),
    getTomorrowPrefetchSummary(),
  ]);

  return NextResponse.json({ slates, reviewQueue, tomorrowPrefetch });
}
