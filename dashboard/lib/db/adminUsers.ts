import { getExecutor } from "./executor";
import { latestRowPerUserSubquery } from "./subscriptions";
import type { SubscriptionStatus } from "./types";

/** A user row joined to their CURRENT (latest-by-insertion-order)
 * subscription, if any -- the shape the admin Users list/filter table is
 * built on. A user with no subscription at all has all subscription_*
 * fields null, not omitted, so the caller can render "No subscription"
 * explicitly. */
export interface AdminUserRow {
  id: string;
  email: string;
  role: string;
  display_name: string | null;
  disabled_at: string | null;
  email_verified_at: string | null;
  created_at: string;
  beta_access_granted_at: string | null;
  subscription_id: string | null;
  plan_id: string | null;
  plan_name: string | null;
  subscription_status: SubscriptionStatus | null;
  trial_ends_at: string | null;
  current_period_end: string | null;
}

export interface AdminUsersFilter {
  search?: string | null;
  role?: string | null;
  planId?: string | null;
  /** A SubscriptionStatus value, or "none" for users with no subscription row at all. */
  subscriptionStatus?: string | null;
  /** "in_trial" = currently trialing; "trial_expired" = trialing but trial_ends_at has already passed. */
  trialStatus?: string | null;
  /** Milestone 30: "granted" / "not_granted" -- filters on
   * users.beta_access_granted_at, independent of role/subscription. */
  betaAccess?: string | null;
  limit?: number;
  offset?: number;
}

function buildWhere(filter: AdminUsersFilter): { where: string; params: (string | number | null)[] } {
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];

  if (filter.search) {
    clauses.push("(LOWER(u.email) LIKE LOWER(?) OR LOWER(u.display_name) LIKE LOWER(?))");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern);
  }
  if (filter.role) {
    clauses.push("u.role = ?");
    params.push(filter.role);
  }
  if (filter.planId) {
    clauses.push("s.plan_id = ?");
    params.push(filter.planId);
  }
  if (filter.subscriptionStatus === "none") {
    clauses.push("s.id IS NULL");
  } else if (filter.subscriptionStatus) {
    clauses.push("s.status = ?");
    params.push(filter.subscriptionStatus);
  }
  if (filter.trialStatus === "in_trial") {
    clauses.push("s.status = 'trialing'");
  } else if (filter.trialStatus === "trial_expired") {
    clauses.push("s.status = 'trialing' AND s.trial_ends_at IS NOT NULL AND s.trial_ends_at < ?");
    params.push(new Date().toISOString());
  }
  if (filter.betaAccess === "granted") {
    clauses.push("u.beta_access_granted_at IS NOT NULL");
  } else if (filter.betaAccess === "not_granted") {
    clauses.push("u.beta_access_granted_at IS NULL");
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  return { where, params };
}

export async function listAdminUsers(filter: AdminUsersFilter = {}): Promise<AdminUserRow[]> {
  const db = getExecutor();
  const { where, params } = buildWhere(filter);
  const limit = filter.limit ?? 50;
  const offset = filter.offset ?? 0;
  const rows = await db.all<Record<string, unknown>>(
    `SELECT u.id, u.email, u.role, u.display_name, u.disabled_at, u.email_verified_at, u.created_at, u.beta_access_granted_at,
            s.id as subscription_id, s.plan_id as plan_id, p.name as plan_name, s.status as subscription_status,
            s.trial_ends_at as trial_ends_at, s.current_period_end as current_period_end
     FROM users u
     LEFT JOIN (${latestRowPerUserSubquery(db)}) s ON s.user_id = u.id
     LEFT JOIN plans p ON p.id = s.plan_id
     ${where}
     ORDER BY u.created_at DESC
     LIMIT ? OFFSET ?`,
    [...params, limit, offset],
  );
  return rows as unknown as AdminUserRow[];
}

export async function countAdminUsers(filter: AdminUsersFilter = {}): Promise<number> {
  const db = getExecutor();
  const { where, params } = buildWhere(filter);
  const row = await db.get<{ c: number }>(
    `SELECT COUNT(*) as c
     FROM users u
     LEFT JOIN (${latestRowPerUserSubquery(db)}) s ON s.user_id = u.id
     ${where}`,
    params,
  );
  return Number(row!.c);
}
