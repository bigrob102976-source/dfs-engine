import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getFeatureFlag, setFeatureFlagState } from "@/lib/db/featureFlags";
import type { FeatureFlagState } from "@/lib/db/types";

export const dynamic = "force-dynamic";

const VALID_STATES: FeatureFlagState[] = ["PRODUCTION", "BETA", "ADMIN_ONLY", "DISABLED"];

export async function PATCH(request: Request, ctx: RouteContext<"/api/admin/features/[key]/state">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  const { key } = await ctx.params;
  const flag = await getFeatureFlag(key);
  if (!flag) return NextResponse.json({ error: "Unknown feature flag." }, { status: 404 });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const { state } = (body ?? {}) as { state?: unknown };
  if (typeof state !== "string" || !(VALID_STATES as string[]).includes(state)) {
    return NextResponse.json({ error: "Invalid feature flag state." }, { status: 400 });
  }

  await setFeatureFlagState(key, state as FeatureFlagState, admin.id);
  await recordAuditLog({
    actorUserId: admin.id,
    actorLabel: admin.email,
    action: "feature_flag_changed",
    targetType: "feature_flag",
    targetId: key,
    metadata: { fromState: flag.state, toState: state },
  });
  return NextResponse.json({ ok: true, flag: await getFeatureFlag(key) });
}
