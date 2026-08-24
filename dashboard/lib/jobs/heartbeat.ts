import { getExecutor } from "../db/executor";
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

/** `ON CONFLICT ... DO UPDATE SET col = excluded.col` is identical syntax
 * on SQLite (3.24+) and PostgreSQL -- no backend branch needed here. */
export async function recordHeartbeat(workerId: string, metadata?: Record<string, unknown>): Promise<void> {
  const db = getExecutor();
  const now = new Date().toISOString();
  await db.run(
    `INSERT INTO worker_heartbeats (worker_id, last_seen_at, status, metadata_json) VALUES (?, ?, 'ONLINE', ?)
     ON CONFLICT(worker_id) DO UPDATE SET last_seen_at = excluded.last_seen_at, metadata_json = excluded.metadata_json`,
    [workerId, now, metadata ? JSON.stringify(metadata) : null],
  );
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

export async function listWorkerHealth(): Promise<WorkerHealth[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM worker_heartbeats ORDER BY worker_id");
  const now = new Date();
  return (rows as unknown as WorkerHeartbeatRow[]).map((row) => ({
    workerId: row.worker_id,
    lastSeenAt: row.last_seen_at,
    health: deriveWorkerHealth(row.last_seen_at, now),
  }));
}

/** True when at least one worker has reported a heartbeat recently
 * enough to be considered ONLINE -- used by /api/health's admin
 * readiness view and the Admin System page's "Worker: ONLINE/OFFLINE"
 * status card. */
export async function isAnyWorkerOnline(): Promise<boolean> {
  const workers = await listWorkerHealth();
  return workers.some((w) => w.health === "ONLINE");
}
