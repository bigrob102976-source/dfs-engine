// Milestone 30: composes SAFE-only readiness for the Admin System page's
// "Production Infrastructure" card -- Database / Object Storage / Job
// Queue / Worker. Never returns a credential value (mirrors every other
// status function in this codebase, e.g. lib/billing/stripeConfig.ts).
// SportsGameOdds and Stripe status are already covered by
// lib/gameEnvironmentStatus.ts and lib/billing/stripeConfig.ts
// respectively -- not duplicated here.

import { ProductionDatabaseNotConfiguredError, resolveDbBackend } from "./db/backend";
import { getDb } from "./db/client";
import { checkPostgresConnection } from "./db/postgresClient";
import { listRecentJobs } from "./jobs/queue";
import { isAnyWorkerOnline, listWorkerHealth, type WorkerHealth } from "./jobs/heartbeat";
import { checkObjectStorageConnection, getObjectStorageConfigStatus, resolveObjectStorageConfigFromEnv } from "./storage/StorageBackend";

export interface DatabaseReadiness {
  kind: "sqlite" | "postgres";
  status: "CONNECTED" | "ERROR";
  detail: string;
}

export async function getDatabaseReadiness(): Promise<DatabaseReadiness> {
  let decision;
  try {
    decision = resolveDbBackend();
  } catch (err) {
    // Production, fail-closed, no DATABASE_URL configured -- a real,
    // expected state to SHOW on this page, not crash it.
    return { kind: "postgres", status: "ERROR", detail: err instanceof ProductionDatabaseNotConfiguredError ? err.message : String(err) };
  }

  if (decision.kind === "postgres") {
    const result = await checkPostgresConnection();
    return { kind: "postgres", status: result.connected ? "CONNECTED" : "ERROR", detail: result.error ?? "Connected." };
  }

  try {
    getDb();
    return { kind: "sqlite", status: "CONNECTED", detail: "Local SQLite database." };
  } catch (err) {
    return { kind: "sqlite", status: "ERROR", detail: err instanceof Error ? err.message : String(err) };
  }
}

export interface ObjectStorageReadiness {
  status: "CONNECTED" | "NOT_CONFIGURED" | "ERROR";
  detail: string;
}

export async function getObjectStorageReadiness(): Promise<ObjectStorageReadiness> {
  const configStatus = getObjectStorageConfigStatus();
  if (!configStatus.configured) {
    return { status: "NOT_CONFIGURED", detail: `Missing: ${configStatus.missing.join(", ")}` };
  }
  const config = resolveObjectStorageConfigFromEnv()!;
  const result = await checkObjectStorageConnection(config);
  return { status: result.connected ? "CONNECTED" : "ERROR", detail: result.error ?? `Bucket "${config.bucket}" reachable.` };
}

export interface JobQueueReadiness {
  status: "CONNECTED" | "ERROR";
  detail: string;
  queuedCount: number | null;
  runningCount: number | null;
}

/** The `jobs` table lives in the same database as everything else, so
 * this necessarily reports the same ERROR the Database card does when
 * Postgres is configured but the query layer hasn't been ported yet
 * (lib/db/client.ts::getDb() throws) -- an honest reflection of the same
 * real gap, not a separate bug. */
export function getJobQueueReadiness(): JobQueueReadiness {
  try {
    const recent = listRecentJobs(200);
    return {
      status: "CONNECTED",
      detail: `${recent.length} job(s) in recent history.`,
      queuedCount: recent.filter((j) => j.status === "QUEUED").length,
      runningCount: recent.filter((j) => j.status === "RUNNING").length,
    };
  } catch (err) {
    return { status: "ERROR", detail: err instanceof Error ? err.message : String(err), queuedCount: null, runningCount: null };
  }
}

export interface WorkerReadiness {
  status: "ONLINE" | "OFFLINE";
  workers: WorkerHealth[];
}

export function getWorkerReadiness(): WorkerReadiness {
  const workers = listWorkerHealth();
  return { status: isAnyWorkerOnline() ? "ONLINE" : "OFFLINE", workers };
}
