import { getExecutor } from "./executor";

export interface DbStats {
  totalUsers: number;
  totalSessions: number;
  totalSubscriptions: number;
  totalAuditLogEntries: number;
}

const COUNTABLE_TABLES = ["users", "sessions", "subscriptions", "admin_audit_log"] as const;

/** Real row counts straight from the configured database -- table names
 * are a fixed internal constant, never user input, so this is not
 * building a query from untrusted data. */
export async function computeDbStats(): Promise<DbStats> {
  const db = getExecutor();
  const counts: Record<string, number> = {};
  for (const table of COUNTABLE_TABLES) {
    const row = await db.get<{ c: number }>(`SELECT COUNT(*) as c FROM ${table}`);
    counts[table] = Number(row!.c);
  }
  return {
    totalUsers: counts.users,
    totalSessions: counts.sessions,
    totalSubscriptions: counts.subscriptions,
    totalAuditLogEntries: counts.admin_audit_log,
  };
}
