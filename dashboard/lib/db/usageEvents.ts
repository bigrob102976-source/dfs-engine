import crypto from "node:crypto";

import { getExecutor } from "./executor";

export async function recordUsageEvent(args: { userId: string | null; eventType: string; metadata?: Record<string, unknown> | null }): Promise<void> {
  const db = getExecutor();
  await db.run("INSERT INTO usage_events (id, user_id, event_type, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)", [
    crypto.randomUUID(),
    args.userId,
    args.eventType,
    args.metadata ? JSON.stringify(args.metadata) : null,
    new Date().toISOString(),
  ]);
}

export async function countUsageEvents(filter: { eventType?: string; since?: string } = {}): Promise<number> {
  const db = getExecutor();
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
  const row = await db.get<{ c: number }>(`SELECT COUNT(*) as c FROM usage_events ${where}`, params);
  return Number(row!.c);
}
