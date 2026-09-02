import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { computeAndPersistEligibilityForSlate } from "@/lib/db/canonicalEligibility";

export const dynamic = "force-dynamic";

/** M6G -- ADMIN-only, manual trigger for computing REAL MLB lineup
 * eligibility for one canonical slate (dfs/eligibility.py, via
 * scripts/compute_canonical_eligibility.py). Never customer-facing.
 *
 * Production-automatic recomputation (research package refresh ->
 * canonical eligibility recomputation, with no admin button press
 * required) is NOT implemented by this route -- see this project's M6
 * final report for exactly what remains before that's true. For now,
 * this mirrors the existing admin "Refresh Data" pattern
 * (slatePipeline.ts's runSlatePipeline, also entirely admin-button-
 * driven today) rather than inventing a new automatic/polling
 * mechanism, per M6G's explicit "prefer reuse" instruction.
 *
 * POST /api/admin/canonical-eligibility { "internalSlateId": "..." } */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const internalSlateId = (body as { internalSlateId?: unknown } | null)?.internalSlateId;
  if (typeof internalSlateId !== "string" || !internalSlateId) {
    return NextResponse.json({ error: "\"internalSlateId\" (string) is required." }, { status: 400 });
  }

  const result = await computeAndPersistEligibilityForSlate(internalSlateId);
  if (result.status === "SLATE_NOT_FOUND") {
    return NextResponse.json({ error: "No canonical slate found with that internalSlateId." }, { status: 404 });
  }
  return NextResponse.json({ result });
}
