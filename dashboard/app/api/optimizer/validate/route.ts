import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { userCanSelectBigMoneyMlOptimizerSource, userCanSelectBlueCollarOptimizerSource } from "@/lib/entitlements/featureVisibility";
import { validateBuildRequest } from "@/lib/optimizerWorkspace/buildRunner";
import { parseBuildRequest } from "@/lib/optimizerWorkspace/parseBuildRequest";

export const dynamic = "force-dynamic";

/** Fast, authoritative pre-solve validation -- runs the real optimizer's
 * own resolve_settings()/pre_solve_diagnostics() logic (never the CP-SAT
 * solver) so the UI can show "here's what's wrong" before the user
 * clicks Build. See optimizer/constraints.py::pre_solve_diagnostics.
 * Milestone 29: any logged-in user may use the optimizer. */
export async function POST(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const parsed = parseBuildRequest(body);
  if (!parsed.ok) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }

  if (parsed.request.projectionSource === "big_money_ml" && !userCanSelectBigMoneyMlOptimizerSource(userOrRes)) {
    return NextResponse.json({ error: "Big Money ML is an ADMIN/OWNER-only optimizer projection source." }, { status: 403 });
  }

  if (parsed.request.projectionSource === "bluecollar" && !userCanSelectBlueCollarOptimizerSource(userOrRes)) {
    return NextResponse.json({ error: "BlueCollar is an ADMIN/OWNER-only optimizer projection source." }, { status: 403 });
  }

  const { errors, coverage } = await validateBuildRequest(parsed.request);
  return NextResponse.json({ errors, coverage });
}
