import crypto from "node:crypto";

import { getDb } from "./client";
import type { User } from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

export function createUser(args: { email: string; passwordHash: string; displayName?: string | null }): User {
  const db = getDb();
  const id = crypto.randomUUID();
  const now = nowIso();
  db.prepare(
    "INSERT INTO users (id, email, password_hash, role, display_name, created_at, updated_at) VALUES (?, ?, ?, 'MEMBER', ?, ?, ?)",
  ).run(id, args.email, args.passwordHash, args.displayName ?? null, now, now);
  return findUserById(id)!;
}

function mapUser(row: Record<string, unknown> | undefined): User | null {
  if (!row) return null;
  return row as unknown as User;
}

export function findUserByEmail(email: string): User | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM users WHERE email = ? COLLATE NOCASE").get(email);
  return mapUser(row);
}

export function findUserById(id: string): User | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM users WHERE id = ?").get(id);
  return mapUser(row);
}

export function updateUserPassword(id: string, passwordHash: string): void {
  const db = getDb();
  db.prepare("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?").run(passwordHash, nowIso(), id);
}

export function setEmailVerified(id: string): void {
  const db = getDb();
  db.prepare("UPDATE users SET email_verified_at = ?, updated_at = ? WHERE id = ?").run(nowIso(), nowIso(), id);
}

export function updateUserRole(id: string, role: string): void {
  const db = getDb();
  db.prepare("UPDATE users SET role = ?, updated_at = ? WHERE id = ?").run(role, nowIso(), id);
}

export function setUserDisabled(id: string, disabled: boolean): void {
  const db = getDb();
  db.prepare("UPDATE users SET disabled_at = ?, updated_at = ? WHERE id = ?").run(disabled ? nowIso() : null, nowIso(), id);
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
export function listUsers(filter: ListUsersFilter = {}): User[] {
  const db = getDb();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];

  if (filter.search) {
    clauses.push("(email LIKE ? OR display_name LIKE ?)");
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
  const rows = db
    .prepare(`SELECT * FROM users ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`)
    .all(...params, limit, offset);
  return rows as unknown as User[];
}

export function countUsers(filter: Pick<ListUsersFilter, "search" | "role"> = {}): number {
  const db = getDb();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];
  if (filter.search) {
    clauses.push("(email LIKE ? OR display_name LIKE ?)");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern);
  }
  if (filter.role) {
    clauses.push("role = ?");
    params.push(filter.role);
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const row = db.prepare(`SELECT COUNT(*) as c FROM users ${where}`).get(...params) as { c: number };
  return row.c;
}

export function countAdmins(): number {
  const db = getDb();
  const row = db.prepare("SELECT COUNT(*) as c FROM users WHERE role = 'ADMIN'").get() as { c: number };
  return row.c;
}

export function setStripeCustomerId(id: string, stripeCustomerId: string): void {
  const db = getDb();
  db.prepare("UPDATE users SET stripe_customer_id = ?, updated_at = ? WHERE id = ?").run(stripeCustomerId, nowIso(), id);
}

export function findUserByStripeCustomerId(stripeCustomerId: string): User | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM users WHERE stripe_customer_id = ?").get(stripeCustomerId);
  return mapUser(row);
}

/** One-trial-policy write path -- idempotent (COALESCE never overwrites
 * an earlier consumption timestamp), and deliberately provider-agnostic:
 * both DevBillingProvider and StripeBillingProvider call this through the
 * same code path, so there is exactly one trial-tracking mechanism. */
export function markTrialConsumed(id: string): void {
  const db = getDb();
  const now = nowIso();
  db.prepare("UPDATE users SET trial_consumed_at = COALESCE(trial_consumed_at, ?), updated_at = ? WHERE id = ?").run(now, now, id);
}
