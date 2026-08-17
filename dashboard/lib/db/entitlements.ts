import crypto from "node:crypto";

import { getDb } from "./client";
import type { Entitlement, UserEntitlement } from "./types";

export function listEntitlementsCatalog(): Entitlement[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM entitlements ORDER BY sport_code, key").all();
  return rows as unknown as Entitlement[];
}

export function listEntitlementsForSport(sportCode: string): Entitlement[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM entitlements WHERE sport_code = ? ORDER BY key").all(sportCode);
  return rows as unknown as Entitlement[];
}

/** Only non-expired explicit grants -- an expired grant is treated as
 * absent, never surfaced as if it still applied. */
export function listUserEntitlements(userId: string): UserEntitlement[] {
  const db = getDb();
  const rows = db
    .prepare(
      "SELECT * FROM user_entitlements WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?) ORDER BY created_at DESC",
    )
    .all(userId, new Date().toISOString());
  return rows as unknown as UserEntitlement[];
}

export function grantUserEntitlement(args: {
  userId: string;
  entitlementKey: string;
  grantedBy: string | null;
  reason?: string | null;
  expiresAt?: string | null;
}): UserEntitlement {
  const db = getDb();
  const id = crypto.randomUUID();
  db.prepare(
    `INSERT INTO user_entitlements (id, user_id, entitlement_key, granted_by, reason, created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id, entitlement_key) DO UPDATE SET
       granted_by = excluded.granted_by, reason = excluded.reason, expires_at = excluded.expires_at, created_at = excluded.created_at`,
  ).run(id, args.userId, args.entitlementKey, args.grantedBy, args.reason ?? null, new Date().toISOString(), args.expiresAt ?? null);
  const row = db
    .prepare("SELECT * FROM user_entitlements WHERE user_id = ? AND entitlement_key = ?")
    .get(args.userId, args.entitlementKey);
  return row as unknown as UserEntitlement;
}

export function revokeUserEntitlement(userId: string, entitlementKey: string): void {
  const db = getDb();
  db.prepare("DELETE FROM user_entitlements WHERE user_id = ? AND entitlement_key = ?").run(userId, entitlementKey);
}
