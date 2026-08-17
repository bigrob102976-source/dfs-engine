import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { isValidRole } from "@/lib/auth/roles";
import { recordAuditLog } from "@/lib/db/auditLog";
import { listUserEntitlements } from "@/lib/db/entitlements";
import { getPlan } from "@/lib/db/plans";
import { deleteAllSessionsForUser } from "@/lib/db/sessions";
import {
  cancelSubscription,
  extendSubscriptionTrial,
  getCurrentSubscriptionForUser,
  insertSubscription,
} from "@/lib/db/subscriptions";
import { countAdmins, findUserById, setUserDisabled, updateUserRole } from "@/lib/db/users";

export const dynamic = "force-dynamic";

async function loadTarget(id: string) {
  const target = findUserById(id);
  if (!target) return null;
  return {
    user: target,
    subscription: getCurrentSubscriptionForUser(id),
    entitlements: listUserEntitlements(id),
  };
}

export async function GET(_request: Request, ctx: RouteContext<"/api/admin/users/[id]">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { id } = await ctx.params;
  const detail = await loadTarget(id);
  if (!detail) return NextResponse.json({ error: "User not found." }, { status: 404 });
  return NextResponse.json(detail);
}

const MAX_TRIAL_EXTENSION_DAYS = 90;

export async function PATCH(request: Request, ctx: RouteContext<"/api/admin/users/[id]">) {
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
  const { action } = (body ?? {}) as { action?: unknown };

  switch (action) {
    case "change_role": {
      const { role } = body as { role?: unknown };
      if (typeof role !== "string" || !isValidRole(role)) {
        return NextResponse.json({ error: "Invalid role." }, { status: 400 });
      }
      if (target.role === "ADMIN" && role !== "ADMIN" && countAdmins() <= 1) {
        return NextResponse.json({ error: "Cannot remove the last remaining admin." }, { status: 400 });
      }
      updateUserRole(target.id, role);
      recordAuditLog({
        actorUserId: admin.id,
        actorLabel: admin.email,
        action: "user_role_changed",
        targetType: "user",
        targetId: target.id,
        metadata: { fromRole: target.role, toRole: role },
      });
      break;
    }

    case "disable_account": {
      setUserDisabled(target.id, true);
      deleteAllSessionsForUser(target.id);
      recordAuditLog({
        actorUserId: admin.id,
        actorLabel: admin.email,
        action: "user_disabled",
        targetType: "user",
        targetId: target.id,
      });
      break;
    }

    case "restore_account": {
      setUserDisabled(target.id, false);
      recordAuditLog({
        actorUserId: admin.id,
        actorLabel: admin.email,
        action: "user_restored",
        targetType: "user",
        targetId: target.id,
      });
      break;
    }

    case "extend_trial": {
      const { days } = body as { days?: unknown };
      if (typeof days !== "number" || !Number.isInteger(days) || days <= 0 || days > MAX_TRIAL_EXTENSION_DAYS) {
        return NextResponse.json({ error: `days must be a whole number between 1 and ${MAX_TRIAL_EXTENSION_DAYS}.` }, { status: 400 });
      }
      const subscription = getCurrentSubscriptionForUser(target.id);
      if (!subscription) {
        return NextResponse.json({ error: "User has no subscription to extend." }, { status: 400 });
      }
      const base = subscription.trial_ends_at && new Date(subscription.trial_ends_at).getTime() > Date.now()
        ? new Date(subscription.trial_ends_at)
        : new Date();
      const newTrialEndsAt = new Date(base.getTime() + days * 24 * 60 * 60 * 1000).toISOString();
      extendSubscriptionTrial(subscription.id, newTrialEndsAt);
      recordAuditLog({
        actorUserId: admin.id,
        actorLabel: admin.email,
        action: "user_trial_extended",
        targetType: "user",
        targetId: target.id,
        metadata: { days, newTrialEndsAt },
      });
      break;
    }

    case "grant_complimentary": {
      const { planId, expiresAt } = body as { planId?: unknown; expiresAt?: unknown };
      if (typeof planId !== "string" || !getPlan(planId)) {
        return NextResponse.json({ error: "Unknown plan." }, { status: 400 });
      }
      if (expiresAt !== undefined && expiresAt !== null && typeof expiresAt !== "string") {
        return NextResponse.json({ error: "expiresAt must be an ISO date string or null." }, { status: 400 });
      }
      insertSubscription({
        userId: target.id,
        planId,
        status: "complimentary",
        currentPeriodEnd: (expiresAt as string | null) ?? null,
      });
      recordAuditLog({
        actorUserId: admin.id,
        actorLabel: admin.email,
        action: "user_granted_complimentary",
        targetType: "user",
        targetId: target.id,
        metadata: { planId, expiresAt: expiresAt ?? null },
      });
      break;
    }

    case "remove_complimentary": {
      const subscription = getCurrentSubscriptionForUser(target.id);
      if (!subscription || subscription.status !== "complimentary") {
        return NextResponse.json({ error: "User does not have an active complimentary grant." }, { status: 400 });
      }
      cancelSubscription(subscription.id);
      recordAuditLog({
        actorUserId: admin.id,
        actorLabel: admin.email,
        action: "user_complimentary_removed",
        targetType: "user",
        targetId: target.id,
      });
      break;
    }

    default:
      return NextResponse.json({ error: "Unknown action." }, { status: 400 });
  }

  const detail = await loadTarget(target.id);
  return NextResponse.json({ ok: true, ...detail });
}
