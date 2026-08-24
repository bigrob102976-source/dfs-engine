// Milestone 30: composes SAFE-only readiness for the Admin System page's
// "Production Infrastructure" card -- Database / Object Storage / Job
// Queue / Worker. Never returns a credential value (mirrors every other
// status function in this codebase, e.g. lib/billing/stripeConfig.ts).
// SportsGameOdds and Stripe status are already covered by
// lib/gameEnvironmentStatus.ts and lib/billing/stripeConfig.ts
// respectively -- not duplicated here.
//
// Milestone 33.1: getDatabaseReadiness() now also reports SCHEMA
// readiness (not just connectivity) -- a fresh Postgres database
// connects fine but has zero tables until migrations are explicitly
// applied (see lib/db/postgresClient.ts::checkPostgresSchemaReadiness's
// own docstring for why this is never done implicitly here).

import { ProductionDatabaseNotConfiguredError, resolveDbBackend } from "./db/backend";
import { getDb } from "./db/client";
import { checkPostgresConnection, checkPostgresSchemaReadiness } from "./db/postgresClient";
import { listRecentJobs } from "./jobs/queue";
import { isAnyWorkerOnline, listWorkerHealth, type WorkerHealth } from "./jobs/heartbeat";
import { ProductionStorageNotConfiguredError, resolveStorageBackend } from "./storage/backend";
import { checkObjectStorageConnection, getObjectStorageConfigStatus, resolveObjectStorageConfigFromEnv } from "./storage/StorageBackend";

export interface DatabaseReadiness {
  kind: "sqlite" | "postgres";
  status: "CONNECTED" | "ERROR";
  /** Postgres: whether every migration file on disk has actually been
   * applied to this database. SQLite: always true once `status` is
   * CONNECTED -- lib/db/client.ts::getDb() applies pending migrations
   * synchronously on open, so an open SQLite connection is by
   * construction fully migrated. */
  schemaReady: boolean;
  detail: string;
}

export async function getDatabaseReadiness(): Promise<DatabaseReadiness> {
  let decision;
  try {
    decision = resolveDbBackend();
  } catch (err) {
    // Production, fail-closed, no DATABASE_URL configured -- a real,
    // expected state to SHOW on this page, not crash it.
    return {
      kind: "postgres",
      status: "ERROR",
      schemaReady: false,
      detail: err instanceof ProductionDatabaseNotConfiguredError ? err.message : String(err),
    };
  }

  if (decision.kind === "postgres") {
    const result = await checkPostgresConnection();
    if (!result.connected) {
      return { kind: "postgres", status: "ERROR", schemaReady: false, detail: result.error ?? "Connection failed." };
    }
    const schema = await checkPostgresSchemaReadiness();
    return {
      kind: "postgres",
      status: "CONNECTED",
      schemaReady: schema.ready,
      detail: schema.ready
        ? `Connected. Schema ready (${schema.appliedCount}/${schema.expectedCount} migrations applied).`
        : `Connected, but schema is NOT ready: ${schema.pending.length} migration(s) pending (${schema.appliedCount}/${schema.expectedCount} applied). Run the production migration command before serving traffic.`,
    };
  }

  try {
    getDb();
    return { kind: "sqlite", status: "CONNECTED", schemaReady: true, detail: "Local SQLite database." };
  } catch (err) {
    return { kind: "sqlite", status: "ERROR", schemaReady: false, detail: err instanceof Error ? err.message : String(err) };
  }
}

export interface ObjectStorageReadiness {
  /** Which backend getStorage() actually resolves to right now -- "local"
   * in dev/test or an explicit ALLOW_LOCAL_STORAGE_IN_PRODUCTION override,
   * "object" once OBJECT_STORAGE_* is configured. Milestone 33.2: this is
   * the field lib/storage/getStorage.ts::getStorage() itself uses to pick
   * an implementation, so this card always reflects the SAME decision the
   * running app is actually making, never a separate/stale computation. */
  backend: "local" | "object";
  status: "CONNECTED" | "NOT_CONFIGURED" | "ERROR";
  detail: string;
}

export async function getObjectStorageReadiness(): Promise<ObjectStorageReadiness> {
  let decision;
  try {
    decision = resolveStorageBackend();
  } catch (err) {
    // Production, fail-closed, no OBJECT_STORAGE_* configured -- a real,
    // expected state to SHOW on this page, not crash it.
    return {
      backend: "object",
      status: "NOT_CONFIGURED",
      detail: err instanceof ProductionStorageNotConfiguredError ? err.message : String(err),
    };
  }

  if (decision.kind === "local") {
    return { backend: "local", status: "CONNECTED", detail: decision.reason };
  }

  const configStatus = getObjectStorageConfigStatus();
  if (!configStatus.configured) {
    return { backend: "object", status: "NOT_CONFIGURED", detail: `Missing: ${configStatus.missing.join(", ")}` };
  }
  const config = resolveObjectStorageConfigFromEnv()!;
  const result = await checkObjectStorageConnection(config);
  return {
    backend: "object",
    status: result.connected ? "CONNECTED" : "ERROR",
    detail: result.error ?? `Bucket "${config.bucket}" reachable.`,
  };
}

export interface JobQueueReadiness {
  status: "CONNECTED" | "ERROR";
  detail: string;
  queuedCount: number | null;
  runningCount: number | null;
}

/** The `jobs` table lives in the same database as everything else, so
 * this necessarily reports the same ERROR the Database card does when
 * the underlying connection/schema isn't ready -- an honest reflection
 * of the same real gap, not a separate bug. */
export async function getJobQueueReadiness(): Promise<JobQueueReadiness> {
  try {
    const recent = await listRecentJobs(200);
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

export async function getWorkerReadiness(): Promise<WorkerReadiness> {
  const workers = await listWorkerHealth();
  return { status: (await isAnyWorkerOnline()) ? "ONLINE" : "OFFLINE", workers };
}
