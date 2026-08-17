import crypto from "node:crypto";

import { getDb } from "./client";
import type { AdminAuditLogEntry } from "./types";

/** Append-only by convention: no update/delete function is exported
 * from this module, and no admin UI route ever edits an existing row.
 * `actorUserId` is null only for genuinely system-initiated events
 * (e.g. the one-time admin bootstrap) -- every human-triggered admin
 * action must pass a real user id. Never pass password/token/card data
 * in `metadata`. */
export function recordAuditLog(args: {
  actorUserId: string | null;
  actorLabel: string;
  action: string;
  targetType?: string | null;
  targetId?: string | null;
  metadata?: Record<string, unknown> | null;
}): AdminAuditLogEntry {
  const db = getDb();
  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  db.prepare(
    `INSERT INTO admin_audit_log (id, actor_user_id, actor_label, action, target_type, target_id, metadata_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    id,
    args.actorUserId,
    args.actorLabel,
    args.action,
    args.targetType ?? null,
    args.targetId ?? null,
    args.metadata ? JSON.stringify(args.metadata) : null,
    createdAt,
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
export function hasAuditAction(action: string): boolean {
  const db = getDb();
  const row = db.prepare("SELECT 1 as found FROM admin_audit_log WHERE action = ? LIMIT 1").get(action);
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

export function listAuditLog(filter: ListAuditLogFilter = {}): AdminAuditLogEntry[] {
  const db = getDb();
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
    clauses.push("(actor_label LIKE ? OR action LIKE ? OR target_type LIKE ?)");
    const pattern = `%${filter.search}%`;
    params.push(pattern, pattern, pattern);
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const limit = filter.limit ?? 100;
  const offset = filter.offset ?? 0;
  const rows = db
    // rowid tiebreaker: audit ordering must stay stable even when two
    // actions land in the same millisecond (e.g. a scripted bulk action).
    .prepare(`SELECT * FROM admin_audit_log ${where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?`)
    .all(...params, limit, offset);
  return rows as unknown as AdminAuditLogEntry[];
}
