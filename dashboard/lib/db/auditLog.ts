import crypto from "node:crypto";

import { getExecutor } from "./executor";
import type { AdminAuditLogEntry } from "./types";

/** Append-only by convention: no update/delete function is exported
 * from this module, and no admin UI route ever edits an existing row.
 * `actorUserId` is null only for genuinely system-initiated events
 * (e.g. the one-time admin bootstrap) -- every human-triggered admin
 * action must pass a real user id. Never pass password/token/card data
 * in `metadata`. */
export async function recordAuditLog(args: {
  actorUserId: string | null;
  actorLabel: string;
  action: string;
  targetType?: string | null;
  targetId?: string | null;
  metadata?: Record<string, unknown> | null;
}): Promise<AdminAuditLogEntry> {
  const db = getExecutor();
  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  await db.run(
    `INSERT INTO admin_audit_log (id, actor_user_id, actor_label, action, target_type, target_id, metadata_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      id,
      args.actorUserId,
      args.actorLabel,
      args.action,
      args.targetType ?? null,
      args.targetId ?? null,
      args.metadata ? JSON.stringify(args.metadata) : null,
      createdAt,
    ],
  );
  return {
    id,
    actor_user_id: args.actorUserId,
    actor_label: args.actorLabel,
    action: args.action,
    target_type: args.targetType ?? null,
    target_id: args.targetId ?? null,
    metadata_json: args.metadata ? JSON.stringify(args.metadata) : null,
    created_at: createdAt,
  };
}

/** Used by the admin-bootstrap guard to enforce "fires exactly once,
 * ever" -- checks for ANY prior row with this action, regardless of
 * target. */
export async function hasAuditAction(action: string): Promise<boolean> {
  const db = getExecutor();
  const row = await db.get<{ found: number }>("SELECT 1 as found FROM admin_audit_log WHERE action = ? LIMIT 1", [action]);
  return Boolean(row);
}

export interface ListAuditLogFilter {
  action?: string | null;
  actorUserId?: string | null;
  targetId?: string | null;
  search?: string | null;
  limit?: number;
  offset?: number;
}

export async function listAuditLog(filter: ListAuditLogFilter = {}): Promise<AdminAuditLogEntry[]> {
  const db = getExecutor();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];

  if (filter.action) {
    clauses.push("action = ?");
    params.push(filter.action);
  }
  if (filter.actorUserId) {
    clauses.push("actor_user_id = ?");
    params.push(filter.actorUserId);
  }
  if (filter.targetId) {
    clauses.push("target_id = ?");
    params.push(filter.targetId);
  }
  if (filter.search) {
    clauses.push("(LOWER(actor_label) LIKE LOWER(?) OR LOWER(action) LIKE LOWER(?) OR LOWER(target_type) LIKE LOWER(?))");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern, pattern);
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const limit = filter.limit ?? 100;
  const offset = filter.offset ?? 0;
  const rows = await db.all<Record<string, unknown>>(
    // `id` (a UUID) is a portable tiebreaker for entries created in the
    // same millisecond (e.g. a scripted bulk action) -- SQLite's rowid
    // has no Postgres equivalent (see the 0009 migration's docstring for
    // the two tables where a tiebreaker alone isn't enough and a real
    // `seq` column was added instead; audit-log ordering only ever needs
    // a STABLE tiebreak, not true insertion order, so `id` is sufficient
    // here without a schema change).
    `SELECT * FROM admin_audit_log ${where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?`,
    [...params, limit, offset],
  );
  return rows as unknown as AdminAuditLogEntry[];
}
