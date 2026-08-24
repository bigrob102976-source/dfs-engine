import crypto from "node:crypto";

import { getExecutor } from "./executor";
import type { Entitlement, UserEntitlement } from "./types";

export async function listEntitlementsCatalog(): Promise<Entitlement[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM entitlements ORDER BY sport_code, key");
  return rows as unknown as Entitlement[];
}

export async function listEntitlementsForSport(sportCode: string): Promise<Entitlement[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM entitlements WHERE sport_code = ? ORDER BY key", [sportCode]);
  return rows as unknown as Entitlement[];
}

/** Only non-expired explicit grants -- an expired grant is treated as
 * absent, never surfaced as if it still applied. */
export async function listUserEntitlements(userId: string): Promise<UserEntitlement[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>(
    "SELECT * FROM user_entitlements WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?) ORDER BY created_at DESC",
    [userId, new Date().toISOString()],
  );
  return rows as unknown as UserEntitlement[];
}

/** `ON CONFLICT ... DO UPDATE SET col = excluded.col` is identical syntax
 * on SQLite (3.24+) and PostgreSQL -- no backend branch needed here. */
export async function grantUserEntitlement(args: {
  userId: string;
  entitlementKey: string;
  grantedBy: string | null;
  reason?: string | null;
  expiresAt?: string | null;
}): Promise<UserEntitlement> {
  const db = getExecutor();
  const id = crypto.randomUUID();
  await db.run(
    `INSERT INTO user_entitlements (id, user_id, entitlement_key, granted_by, reason, created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id, entitlement_key) DO UPDATE SET
       granted_by = excluded.granted_by, reason = excluded.reason, expires_at = excluded.expires_at, created_at = excluded.created_at`,
    [id, args.userId, args.entitlementKey, args.grantedBy, args.reason ?? null, new Date().toISOString(), args.expiresAt ?? null],
  );
  const row = await db.get<Record<string, unknown>>("SELECT * FROM user_entitlements WHERE user_id = ? AND entitlement_key = ?", [
    args.userId,
    args.entitlementKey,
  ]);
  return row as unknown as UserEntitlement;
}

export async function revokeUserEntitlement(userId: string, entitlementKey: string): Promise<void> {
  const db = getExecutor();
  await db.run("DELETE FROM user_entitlements WHERE user_id = ? AND entitlement_key = ?", [userId, entitlementKey]);
}
