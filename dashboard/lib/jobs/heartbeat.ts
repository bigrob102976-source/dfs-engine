import { getDb } from "../db/client";
import type { WorkerHealthStatus, WorkerHeartbeatRow } from "../db/types";

// Milestone 30: worker liveness, derived ENTIRELY from a DB timestamp
// (worker_heartbeats.last_seen_at), never from in-process memory -- a
// worker process restarting, or the web process restarting, must not by
// itself make a live worker look offline or vice versa. This is what
// lets the Admin System page show "Worker ONLINE/STALE/OFFLINE" honestly
// even though the web process serving that page and the worker actually
// executing jobs can be two different processes (or, once truly hosted,
// two different machines).

const ONLINE_THRESHOLD_MS = 30_000; // heartbeat within the last 30s
const STALE_THRESHOLD_MS = 120_000; // 30s-2min: worker likely mid-job or briefly hung

export function recordHeartbeat(workerId: string, metadata?: Record<string, unknown>): void {
  const db = getDb();
  const now = new Date().toISOString();
  db.prepare(
    `INSERT INTO worker_heartbeats (worker_id, last_seen_at, status, metadata_json) VALUES (?, ?, 'ONLINE', ?)
     ON CONFLICT(worker_id) DO UPDATE SET last_seen_at = excluded.last_seen_at, metadata_json = excluded.metadata_json`,
  ).run(workerId, now, metadata ? JSON.stringify(metadata) : null);
}

export function deriveWorkerHealth(lastSeenAtIso: string, now: Date = new Date()): WorkerHealthStatus {
  const ageMs = now.getTime() - new Date(lastSeenAtIso).getTime();
  if (ageMs <= ONLINE_THRESHOLD_MS) return "ONLINE";
  if (ageMs <= STALE_THRESHOLD_MS) return "STALE";
  return "OFFLINE";
}

export interface WorkerHealth {
  workerId: string;
  lastSeenAt: string;
  health: WorkerHealthStatus;
}

export function listWorkerHealth(): WorkerHealth[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM worker_heartbeats ORDER BY worker_id").all() as unknown as WorkerHeartbeatRow[];
  const now = new Date();
  return rows.map((row) => ({ workerId: row.worker_id, lastSeenAt: row.last_seen_at, health: deriveWorkerHealth(row.last_seen_at, now) }));
}

/** True when at least one worker has reported a heartbeat recently
 * enough to be considered ONLINE -- used by /api/health's admin
 * readiness view and the Admin System page's "Worker: ONLINE/OFFLINE"
 * status card. */
export function isAnyWorkerOnline(): boolean {
  return listWorkerHealth().some((w) => w.health === "ONLINE");
}
