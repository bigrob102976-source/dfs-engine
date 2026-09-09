import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { filterSlatesForCurrentViewer } from "@/lib/memberSlateVisibility";
import { resolveSlateDate } from "@/lib/slateDate";
import { resolveServingBackend } from "@/lib/servingBackend/config";
import type { ServingBackendKind } from "@/lib/servingBackend/types";

export const dynamic = "force-dynamic";

/** Every DFS slate the configured provider currently exposes for a
 * date. Milestone 31.2C: accepts an optional `?date=YYYY-MM-DD` query
 * param; omitted/empty falls back to today's America/Chicago date
 * exactly as before (fully backward compatible) -- see
 * lib/slateDate.ts. A present-but-invalid date is rejected with 400.
 * Milestone 29: requires login; a non-admin viewer only ever sees
 * PUBLISHED slates here too (lib/memberSlateVisibility.ts), same rule
 * as every /dashboard/* page's slate list. "Published" is defined by
 * whichever backend served the list, which is why `backend.kind` is
 * passed through -- for canonical, promotion IS publication, and
 * consulting the legacy `slate_status` table there would filter every
 * slate away (see memberSlateVisibility.ts's docstring).
 *
 * The serving backend is chosen by resolveServingBackend(); since
 * 2026-09-08 canonical is the DEFAULT for any user the
 * 'mlb.canonical_postgres_serving' flag covers, and an explicit
 * `?servingBackend=LEGACY_R2` is honored as a per-request escape
 * hatch. An explicit CANONICAL_POSTGRES can never grant access the
 * flag does not already give -- there is no way to bypass this
 * server-side. */
export async function GET(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const { searchParams } = new URL(request.url);
  const dateResolution = resolveSlateDate(searchParams.get("date"));
  if (!dateResolution.ok) {
    return NextResponse.json({ error: dateResolution.error }, { status: 400 });
  }
  const date = dateResolution.date;
  const requestedBackend = searchParams.get("servingBackend") as ServingBackendKind | null;

  const backend = await resolveServingBackend(user, requestedBackend);
  const result = await backend.listSlates(date);
  const slates = await filterSlatesForCurrentViewer(result.slates, date, backend.kind);
  return NextResponse.json({ date, ...result, slates, servingBackend: backend.kind });
}
