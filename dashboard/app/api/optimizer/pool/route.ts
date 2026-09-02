import { NextResponse } from "next/server";

import { requireAdminApi, requireAuthApi } from "@/lib/auth/guards";
import { loadPool } from "@/lib/optimizerWorkspace/poolCache";
import { isValidSlateId } from "@/lib/optimizerWorkspace/validateSlateId";
import { resolveSlateDate } from "@/lib/slateDate";
import { resolveServingBackend } from "@/lib/servingBackend/config";
import type { ServingBackendKind } from "@/lib/servingBackend/types";

export const dynamic = "force-dynamic";

/** Selects a slate and loads (or rebuilds) its player pool: fetch ->
 * build pool -> project ownership, via the same immutable-artifact
 * Python scripts the one-click refresh pipeline uses. Body:
 * { "slateId": "...", "date"?: "YYYY-MM-DD", "forceRefresh"?: boolean,
 *   "servingBackend"?: "CANONICAL_POSTGRES" }.
 * Milestone 31.2C: `date` is optional -- omitted/empty falls back to
 * today's America/Chicago date exactly as before (fully backward
 * compatible); an explicit date lets the caller load a slate for a date
 * other than "today" (e.g. when a live DK slate has already rolled to
 * the next calendar day ahead of the Chicago-today boundary -- see
 * lib/slateDate.ts's module docstring). A present-but-invalid date is
 * rejected with 400 rather than silently substituted.
 * Milestone 29: any logged-in user may LOAD a slate's pool ("use
 * optimizer" is a MEMBER-permitted action) -- but forceRefresh actually
 * triggers a real backend rebuild (equivalent to /api/slates/refresh),
 * which is an admin-only "refresh backend slate data" action.
 *
 * M5I: `servingBackend: "CANONICAL_POSTGRES"` is honored ONLY when
 * resolveServingBackend() confirms the requesting user currently passes
 * the 'mlb.canonical_postgres_serving' feature flag (ADMIN_ONLY by
 * default) -- a MEMBER passing this field gets the exact same
 * LEGACY_R2-served pool as omitting it. `forceRefresh` is meaningless
 * for canonical serving (there is no live-refetch concept here -- the
 * canonical backend only ever reads already-promoted worker-acquired
 * data) and is silently ignored in that case. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const slateId = (body as { slateId?: unknown } | null)?.slateId;
  const forceRefresh = Boolean((body as { forceRefresh?: unknown } | null)?.forceRefresh);
  const dateCandidate = (body as { date?: unknown } | null)?.date;
  const requestedBackend = (body as { servingBackend?: unknown } | null)?.servingBackend as ServingBackendKind | undefined;

  if (!isValidSlateId(slateId)) {
    return NextResponse.json({ error: "\"slateId\" (string) is required." }, { status: 400 });
  }
  const dateResolution = resolveSlateDate(dateCandidate);
  if (!dateResolution.ok) {
    return NextResponse.json({ error: dateResolution.error }, { status: 400 });
  }

  const userOrRes = forceRefresh ? await requireAdminApi() : await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const backend = await resolveServingBackend(user, requestedBackend);
  try {
    const pool =
      backend.kind === "CANONICAL_POSTGRES"
        ? await backend.getSlatePool(dateResolution.date, slateId)
        : await loadPool(dateResolution.date, slateId, forceRefresh);
    return NextResponse.json({ pool, servingBackend: backend.kind });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 502 });
  }
}
