import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { checkCanonicalLineupLegality } from "@/lib/db/canonicalLineupLegalityCheck";

export const dynamic = "force-dynamic";

/** M6L -- ADMIN-only, READ-ONLY structural (non-projection) proof that
 * a canonical slate's real, optimizer-eligible players can produce
 * legal DK Classic MLB lineups (roster rules + salary cap + locks/
 * excludes + multi-lineup uniqueness). Never invokes the real CP-SAT
 * optimizer and never writes anything -- see canonicalLineupLegalityCheck.ts's
 * own docstring for exactly why this exists alongside (not instead of)
 * the real optimizer bridge (buildRunner.ts).
 *
 * POST /api/admin/canonical-lineup-check
 *   { "internalSlateId": "...", "count"?: number, "locks"?: string[], "excludes"?: string[] } */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const b = body as Record<string, unknown> | null;
  const internalSlateId = b?.internalSlateId;
  if (typeof internalSlateId !== "string" || !internalSlateId) {
    return NextResponse.json({ error: "\"internalSlateId\" (string) is required." }, { status: 400 });
  }
  const count = typeof b?.count === "number" && Number.isInteger(b.count) && b.count > 0 && b.count <= 20 ? b.count : 1;
  const locks = Array.isArray(b?.locks) ? (b.locks as unknown[]).filter((v): v is string => typeof v === "string") : [];
  const excludes = Array.isArray(b?.excludes) ? (b.excludes as unknown[]).filter((v): v is string => typeof v === "string") : [];

  const result = await checkCanonicalLineupLegality(internalSlateId, { count, locks, excludes });
  if (result.status === "SLATE_NOT_FOUND") {
    return NextResponse.json({ error: "No canonical slate found with that internalSlateId." }, { status: 404 });
  }
  return NextResponse.json({ result });
}
