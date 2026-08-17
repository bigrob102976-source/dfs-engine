import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { grantUserEntitlement, listEntitlementsCatalog, revokeUserEntitlement } from "@/lib/db/entitlements";
import { findUserById } from "@/lib/db/users";

export const dynamic = "force-dynamic";

function isKnownEntitlementKey(key: string): boolean {
  return listEntitlementsCatalog().some((e) => e.key === key);
}

export async function POST(request: Request, ctx: RouteContext<"/api/admin/users/[id]/entitlements">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  const { id } = await ctx.params;
  const target = findUserById(id);
  if (!target) return NextResponse.json({ error: "User not found." }, { status: 404 });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const { entitlementKey, reason, expiresAt } = (body ?? {}) as {
    entitlementKey?: unknown;
    reason?: unknown;
    expiresAt?: unknown;
  };
  if (typeof entitlementKey !== "string" || !isKnownEntitlementKey(entitlementKey)) {
    return NextResponse.json({ error: "Unknown entitlement key." }, { status: 400 });
  }

  const grant = grantUserEntitlement({
    userId: target.id,
    entitlementKey,
    grantedBy: admin.id,
    reason: typeof reason === "string" ? reason : null,
    expiresAt: typeof expiresAt === "string" ? expiresAt : null,
  });
  recordAuditLog({
    actorUserId: admin.id,
    actorLabel: admin.email,
    action: "user_entitlement_granted",
    targetType: "user",
    targetId: target.id,
    metadata: { entitlementKey, reason: reason ?? null, expiresAt: expiresAt ?? null },
  });
  return NextResponse.json({ ok: true, grant });
}

export async function DELETE(request: Request, ctx: RouteContext<"/api/admin/users/[id]/entitlements">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  const { id } = await ctx.params;
  const target = findUserById(id);
  if (!target) return NextResponse.json({ error: "User not found." }, { status: 404 });

  const url = new URL(request.url);
  const entitlementKey = url.searchParams.get("entitlementKey");
  if (!entitlementKey) {
    return NextResponse.json({ error: "entitlementKey query param is required." }, { status: 400 });
  }

  revokeUserEntitlement(target.id, entitlementKey);
  recordAuditLog({
    actorUserId: admin.id,
    actorLabel: admin.email,
    action: "user_entitlement_revoked",
    targetType: "user",
    targetId: target.id,
    metadata: { entitlementKey },
  });
  return NextResponse.json({ ok: true });
}
