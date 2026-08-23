import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { userCanSelectBigMoneyMlOptimizerSource, userCanSelectBlueCollarOptimizerSource } from "@/lib/entitlements/featureVisibility";
import { buildLineups } from "@/lib/optimizerWorkspace/buildRunner";
import { parseBuildRequest } from "@/lib/optimizerWorkspace/parseBuildRequest";

export const dynamic = "force-dynamic";

/** Builds N lineups against the currently-selected slate's player pool.
 * The only fields accepted are the ones parseBuildRequest validates into
 * a well-typed OptimizerBuildRequest -- nothing here can pass an
 * arbitrary flag, path, or shell content to the Python subprocess (see
 * buildRunner.ts::buildArgv, which only ever emits the fixed set of
 * flags scripts/optimize_dk_lineups.py's own CLI already defines). Every
 * successful build persists an immutable lineup set via the same
 * optimizer/persistence.py every other optimizer run in this project
 * uses. Milestone 29: any logged-in user (member or admin) may use the
 * optimizer -- "use optimizer" is explicitly a MEMBER-permitted action. */
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

  // Milestone 32.4: Big Money ML optimizer selection is ADMIN/OWNER-only
  // (feature flag 'mlb.big_money_ml_optimizer', default ADMIN_ONLY) --
  // enforced here server-side, never trusting the UI selector alone.
  if (parsed.request.projectionSource === "big_money_ml" && !userCanSelectBigMoneyMlOptimizerSource(userOrRes)) {
    return NextResponse.json({ error: "Big Money ML is an ADMIN/OWNER-only optimizer projection source." }, { status: 403 });
  }

  // BlueCollar Live Projection Integration: same ADMIN/OWNER-only gate
  // (feature flag 'mlb.bluecollar_optimizer', default ADMIN_ONLY) --
  // enforced here server-side, never trusting the UI selector alone.
  if (parsed.request.projectionSource === "bluecollar" && !userCanSelectBlueCollarOptimizerSource(userOrRes)) {
    return NextResponse.json({ error: "BlueCollar is an ADMIN/OWNER-only optimizer projection source." }, { status: 403 });
  }

  const result = await buildLineups(parsed.request);
  return NextResponse.json({ result }, { status: result.ok ? 200 : 422 });
}
