import crypto from "node:crypto";

import { getExecutor } from "./executor";
import type { User } from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

export async function createUser(args: { email: string; passwordHash: string; displayName?: string | null }): Promise<User> {
  const db = getExecutor();
  const id = crypto.randomUUID();
  const now = nowIso();
  await db.run(
    "INSERT INTO users (id, email, password_hash, role, display_name, created_at, updated_at) VALUES (?, ?, ?, 'MEMBER', ?, ?, ?)",
    [id, args.email, args.passwordHash, args.displayName ?? null, now, now],
  );
  return (await findUserById(id))!;
}

function mapUser(row: Record<string, unknown> | undefined): User | null {
  if (!row) return null;
  return row as unknown as User;
}

/** Case-insensitive by LOWER(email) on both backends -- SQLite's
 * `COLLATE NOCASE` and Postgres's functional `idx_users_email_lower`
 * index (lib/db/migrations-postgres/0001_init.sql) both exist specifically
 * so this exact comparison uses each backend's real unique index rather
 * than a full scan. */
export async function findUserByEmail(email: string): Promise<User | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", [email]);
  return mapUser(row);
}

export async function findUserById(id: string): Promise<User | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM users WHERE id = ?", [id]);
  return mapUser(row);
}

export async function updateUserPassword(id: string, passwordHash: string): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", [passwordHash, nowIso(), id]);
}

export async function setEmailVerified(id: string): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE users SET email_verified_at = ?, updated_at = ? WHERE id = ?", [nowIso(), nowIso(), id]);
}

export async function updateUserRole(id: string, role: string): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE users SET role = ?, updated_at = ? WHERE id = ?", [role, nowIso(), id]);
}

export async function setUserDisabled(id: string, disabled: boolean): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE users SET disabled_at = ?, updated_at = ? WHERE id = ?", [disabled ? nowIso() : null, nowIso(), id]);
}

/** Milestone 30: Private Beta gate (PRIVATE_BETA=true -- see lib/env.ts
 * and lib/auth/betaAccess.ts). granted=true records WHO granted it
 * (grantedByUserId, an admin's id) alongside WHEN; granted=false clears
 * both columns. This is an account-level access gate, not an
 * entitlement -- see the 0005 migration's docstring for why it isn't
 * modeled as a user_entitlements row. */
export async function setBetaAccess(id: string, granted: boolean, grantedByUserId: string | null): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE users SET beta_access_granted_at = ?, beta_access_granted_by = ?, updated_at = ? WHERE id = ?", [
    granted ? nowIso() : null,
    granted ? grantedByUserId : null,
    nowIso(),
    id,
  ]);
}

export interface ListUsersFilter {
  search?: string | null;
  role?: string | null;
  limit?: number;
  offset?: number;
}

/** Plain (role-only) listing -- subscription-status filtering is applied
 * by the caller (lib/db/subscriptions.ts's admin listing joins against
 * this), since "current subscription status" isn't a users-table column. */
export async function listUsers(filter: ListUsersFilter = {}): Promise<User[]> {
  const db = getExecutor();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];

  if (filter.search) {
    clauses.push("(LOWER(email) LIKE LOWER(?) OR LOWER(display_name) LIKE LOWER(?))");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern);
  }
  if (filter.role) {
    clauses.push("role = ?");
    params.push(filter.role);
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const limit = filter.limit ?? 100;
  const offset = filter.offset ?? 0;
  const rows = await db.all<Record<string, unknown>>(`SELECT * FROM users ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`, [
    ...params,
    limit,
    offset,
  ]);
  return rows as unknown as User[];
}

export async function countUsers(filter: Pick<ListUsersFilter, "search" | "role"> = {}): Promise<number> {
  const db = getExecutor();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];
  if (filter.search) {
    clauses.push("(LOWER(email) LIKE LOWER(?) OR LOWER(display_name) LIKE LOWER(?))");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern);
  }
  if (filter.role) {
    clauses.push("role = ?");
    params.push(filter.role);
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const row = await db.get<{ c: number }>(`SELECT COUNT(*) as c FROM users ${where}`, params);
  return Number(row!.c);
}

export async function countAdmins(): Promise<number> {
  const db = getExecutor();
  const row = await db.get<{ c: number }>("SELECT COUNT(*) as c FROM users WHERE role = 'ADMIN'");
  return Number(row!.c);
}

export async function setStripeCustomerId(id: string, stripeCustomerId: string): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE users SET stripe_customer_id = ?, updated_at = ? WHERE id = ?", [stripeCustomerId, nowIso(), id]);
}

export async function findUserByStripeCustomerId(stripeCustomerId: string): Promise<User | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>("SELECT * FROM users WHERE stripe_customer_id = ?", [stripeCustomerId]);
  return mapUser(row);
}

/** One-trial-policy write path -- idempotent (COALESCE never overwrites
 * an earlier consumption timestamp), and deliberately provider-agnostic:
 * both DevBillingProvider and StripeBillingProvider call this through the
 * same code path, so there is exactly one trial-tracking mechanism. */
export async function markTrialConsumed(id: string): Promise<void> {
  const db = getExecutor();
  const now = nowIso();
  await db.run("UPDATE users SET trial_consumed_at = COALESCE(trial_consumed_at, ?), updated_at = ? WHERE id = ?", [now, now, id]);
}
