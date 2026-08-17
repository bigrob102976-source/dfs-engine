import { getDb } from "./client";

export interface DbStats {
  totalUsers: number;
  totalSessions: number;
  totalSubscriptions: number;
  totalAuditLogEntries: number;
}

const COUNTABLE_TABLES = ["users", "sessions", "subscriptions", "admin_audit_log"] as const;

/** Real row counts straight from the local SQLite DB -- table names are
 * a fixed internal constant, never user input, so this is not building
 * a query from untrusted data. */
export function computeDbStats(): DbStats {
  const db = getDb();
  const counts = Object.fromEntries(
    COUNTABLE_TABLES.map((table) => [table, (db.prepare(`SELECT COUNT(*) as c FROM ${table}`).get() as { c: number }).c]),
  );
  return {
    totalUsers: counts.users,
    totalSessions: counts.sessions,
    totalSubscriptions: counts.subscriptions,
    totalAuditLogEntries: counts.admin_audit_log,
  };
}
