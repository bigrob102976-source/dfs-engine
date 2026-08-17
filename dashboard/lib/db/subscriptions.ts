import crypto from "node:crypto";

import { getDb } from "./client";
import type { BillingProviderName, Subscription, SubscriptionStatus } from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

export function insertSubscription(args: {
  userId: string;
  planId: string;
  status: SubscriptionStatus;
  provider?: BillingProviderName;
  providerSubscriptionId?: string | null;
  providerPriceId?: string | null;
  trialEndsAt?: string | null;
  currentPeriodStart?: string | null;
  currentPeriodEnd?: string | null;
  cancelAtPeriodEnd?: boolean;
  lastStripeEventAt?: string | null;
}): Subscription {
  const db = getDb();
  const id = crypto.randomUUID();
  const now = nowIso();
  db.prepare(
    `INSERT INTO subscriptions (
       id, user_id, plan_id, status, provider, provider_subscription_id, provider_price_id,
       trial_ends_at, current_period_start, current_period_end, cancel_at_period_end,
       last_stripe_event_at, created_at, updated_at
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    id,
    args.userId,
    args.planId,
    args.status,
    args.provider ?? "dev",
    args.providerSubscriptionId ?? null,
    args.providerPriceId ?? null,
    args.trialEndsAt ?? null,
    args.currentPeriodStart ?? null,
    args.currentPeriodEnd ?? null,
    args.cancelAtPeriodEnd ? 1 : 0,
    args.lastStripeEventAt ?? null,
    now,
    now,
  );
  return getSubscriptionById(id)!;
}

/** The one place a local subscription row is looked up by its Stripe
 * subscription ID -- used by webhook handlers to decide insert-vs-update,
 * and by the admin "Resync from Stripe" action. */
export function findSubscriptionByProviderSubscriptionId(providerSubscriptionId: string): Subscription | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM subscriptions WHERE provider_subscription_id = ?").get(providerSubscriptionId);
  return (row as unknown as Subscription) ?? null;
}

export function getSubscriptionById(id: string): Subscription | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM subscriptions WHERE id = ?").get(id);
  return (row as unknown as Subscription) ?? null;
}

/** The user's most recent subscription row -- a user has at most one
 * MEANINGFUL "current" subscription at a time in this milestone's model
 * (no concurrent multi-plan support yet), but old rows are kept for
 * history rather than overwritten. Ordered by rowid (SQLite's own
 * monotonic insertion-order column) as the primary key, not created_at:
 * two rows inserted in rapid succession (e.g. an admin cancels then
 * immediately re-subscribes a user) can share the same millisecond
 * timestamp, which would otherwise make "most recent" ambiguous. */
export function getCurrentSubscriptionForUser(userId: string): Subscription | null {
  const db = getDb();
  const row = db
    .prepare("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY rowid DESC LIMIT 1")
    .get(userId);
  return (row as unknown as Subscription) ?? null;
}

export interface ListSubscriptionsFilter {
  status?: SubscriptionStatus | null;
  planId?: string | null;
  search?: string | null;
  limit?: number;
  offset?: number;
}

export interface SubscriptionWithUser extends Subscription {
  user_email: string;
  user_display_name: string | null;
  user_stripe_customer_id: string | null;
  plan_name: string;
  plan_price_cents: number;
}

export function listSubscriptions(filter: ListSubscriptionsFilter = {}): SubscriptionWithUser[] {
  const db = getDb();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];

  if (filter.status) {
    clauses.push("s.status = ?");
    params.push(filter.status);
  }
  if (filter.planId) {
    clauses.push("s.plan_id = ?");
    params.push(filter.planId);
  }
  if (filter.search) {
    clauses.push("(u.email LIKE ? OR u.display_name LIKE ?)");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern);
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const limit = filter.limit ?? 100;
  const offset = filter.offset ?? 0;
  const rows = db
    .prepare(
      `SELECT s.*, u.email as user_email, u.display_name as user_display_name, u.stripe_customer_id as user_stripe_customer_id,
              p.name as plan_name, p.price_cents as plan_price_cents
       FROM subscriptions s
       JOIN users u ON u.id = s.user_id
       JOIN plans p ON p.id = s.plan_id
       ${where}
       ORDER BY s.created_at DESC
       LIMIT ? OFFSET ?`,
    )
    .all(...params, limit, offset);
  return rows as unknown as SubscriptionWithUser[];
}

// Both KPI helpers below count each USER once, by their single most
// recent subscription row (same "latest row per user" definition as
// getCurrentSubscriptionForUser) -- a user who canceled a weekly plan
// and later started a monthly trial has TWO rows in the table (the old
// one is kept for history, never deleted), and a naive GROUP BY over
// every row would double-count them under both "canceled" and
// "trialing" simultaneously.
export const LATEST_ROW_PER_USER_SUBQUERY = `
  SELECT s.* FROM subscriptions s
  WHERE s.rowid = (SELECT MAX(s2.rowid) FROM subscriptions s2 WHERE s2.user_id = s.user_id)
`;

export function countSubscriptionsByStatus(): Record<SubscriptionStatus, number> {
  const db = getDb();
  const rows = db
    .prepare(`SELECT status, COUNT(*) as c FROM (${LATEST_ROW_PER_USER_SUBQUERY}) GROUP BY status`)
    .all() as Array<{ status: SubscriptionStatus; c: number }>;
  const result: Record<SubscriptionStatus, number> = {
    trialing: 0,
    active: 0,
    past_due: 0,
    canceled: 0,
    expired: 0,
    complimentary: 0,
  };
  for (const row of rows) result[row.status] = row.c;
  return result;
}

/** Count of users whose CURRENT subscription is on `planId` and in an
 * access-granting status (trialing/active/complimentary) -- the basis
 * for the Overview page's "Weekly Members"/"Monthly Members" cards. */
export function countCurrentSubscribersByPlan(planId: string): number {
  const db = getDb();
  const row = db
    .prepare(
      `SELECT COUNT(*) as c FROM (${LATEST_ROW_PER_USER_SUBQUERY})
       WHERE plan_id = ? AND status IN ('trialing', 'active', 'complimentary')`,
    )
    .get(planId) as { c: number };
  return row.c;
}

/** Count of users whose CURRENT subscription is on `planId` and actively
 * PAYING (status='active' -- excludes trialing/complimentary, which are
 * real subscribers but generate no revenue). Basis for MRR. */
export function countActiveSubscribersByPlan(planId: string): number {
  const db = getDb();
  const row = db
    .prepare(`SELECT COUNT(*) as c FROM (${LATEST_ROW_PER_USER_SUBQUERY}) WHERE plan_id = ? AND status = 'active'`)
    .get(planId) as { c: number };
  return row.c;
}

export interface TrialConversionStats {
  trialUsersEver: number;
  converted: number;
}

/** Of every user who has EVER had a subscription row that included a
 * trial period, how many are currently `active`. Used for the Trial
 * Conversion KPI -- returns 0/0 (caller treats as "--") when no one has
 * ever trialed.
 *
 * Deliberately keyed on `trial_ends_at IS NOT NULL` rather than
 * `status = 'trialing'`: updateSubscriptionStatus() mutates a row's
 * status IN PLACE (trialing -> active is the SAME row, not a new one),
 * so by the time a user converts, no row is left with status='trialing'
 * to find. trial_ends_at is set once at insert and never cleared by a
 * status transition, so it survives as a reliable "this subscription
 * had a trial" marker regardless of current status. */
export function getTrialConversionStats(): TrialConversionStats {
  const db = getDb();
  const trialUsersEver = (
    db.prepare("SELECT COUNT(DISTINCT user_id) as c FROM subscriptions WHERE trial_ends_at IS NOT NULL").get() as {
      c: number;
    }
  ).c;
  const converted = (
    db
      .prepare(
        `SELECT COUNT(*) as c FROM (${LATEST_ROW_PER_USER_SUBQUERY}) latest
         WHERE latest.status = 'active'
         AND latest.user_id IN (SELECT DISTINCT user_id FROM subscriptions WHERE trial_ends_at IS NOT NULL)`,
      )
      .get() as { c: number }
  ).c;
  return { trialUsersEver, converted };
}

/** Real subscribe-action counts/cancellations within a given period --
 * basis for the Revenue admin page's "New Subscribers" / "Cancellations"
 * cards. Counts ROWS (subscribe/cancel actions), not distinct users --
 * a user who re-subscribes twice in one month is two new-subscriber
 * events, which is the correct interpretation for a revenue page. */
export function countSubscriptionsCreatedSince(sinceIso: string): number {
  const db = getDb();
  const row = db.prepare("SELECT COUNT(*) as c FROM subscriptions WHERE created_at >= ?").get(sinceIso) as { c: number };
  return row.c;
}

export function countCancellationsSince(sinceIso: string): number {
  const db = getDb();
  const row = db
    .prepare("SELECT COUNT(*) as c FROM subscriptions WHERE status = 'canceled' AND canceled_at IS NOT NULL AND canceled_at >= ?")
    .get(sinceIso) as { c: number };
  return row.c;
}

export type UpdateSubscriptionStatusPatch = Partial<
  Pick<
    Subscription,
    "current_period_start" | "current_period_end" | "canceled_at" | "cancel_at_period_end" | "provider_price_id" | "last_stripe_event_at"
  >
>;

export function updateSubscriptionStatus(id: string, status: SubscriptionStatus, patch: UpdateSubscriptionStatusPatch = {}): void {
  const db = getDb();
  db.prepare(
    `UPDATE subscriptions SET
       status = ?,
       current_period_start = COALESCE(?, current_period_start),
       current_period_end = COALESCE(?, current_period_end),
       canceled_at = COALESCE(?, canceled_at),
       cancel_at_period_end = COALESCE(?, cancel_at_period_end),
       provider_price_id = COALESCE(?, provider_price_id),
       last_stripe_event_at = COALESCE(?, last_stripe_event_at),
       updated_at = ?
     WHERE id = ?`,
  ).run(
    status,
    patch.current_period_start ?? null,
    patch.current_period_end ?? null,
    patch.canceled_at ?? null,
    patch.cancel_at_period_end ?? null,
    patch.provider_price_id ?? null,
    patch.last_stripe_event_at ?? null,
    nowIso(),
    id,
  );
}

export function cancelSubscription(id: string): void {
  updateSubscriptionStatus(id, "canceled", { canceled_at: nowIso() });
}

/** Used by the admin "Extend Trial" action -- sets trial_ends_at
 * directly (updateSubscriptionStatus doesn't touch that column). Does
 * not change status, so it's safe to call on an already-trialing
 * subscription without disturbing anything else. */
export function extendSubscriptionTrial(id: string, newTrialEndsAt: string): void {
  const db = getDb();
  db.prepare("UPDATE subscriptions SET trial_ends_at = ?, updated_at = ? WHERE id = ?").run(newTrialEndsAt, nowIso(), id);
}
