import crypto from "node:crypto";

import { getDb } from "./client";

export function recordUsageEvent(args: { userId: string | null; eventType: string; metadata?: Record<string, unknown> | null }): void {
  const db = getDb();
  db.prepare("INSERT INTO usage_events (id, user_id, event_type, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)").run(
    crypto.randomUUID(),
    args.userId,
    args.eventType,
    args.metadata ? JSON.stringify(args.metadata) : null,
    new Date().toISOString(),
  );
}

export function countUsageEvents(filter: { eventType?: string; since?: string } = {}): number {
  const db = getDb();
  const clauses: string[] = [];
  const params: (string | number | null)[] = [];
  if (filter.eventType) {
    clauses.push("event_type = ?");
    params.push(filter.eventType);
  }
  if (filter.since) {
    clauses.push("created_at >= ?");
    params.push(filter.since);
  }
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const row = db.prepare(`SELECT COUNT(*) as c FROM usage_events ${where}`).get(...params) as { c: number };
  return row.c;
}
