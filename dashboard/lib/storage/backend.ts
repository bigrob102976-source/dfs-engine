import { isProduction } from "../env";
import { resolveObjectStorageConfigFromEnv } from "./StorageBackend";

// Milestone 30: mirrors lib/db/backend.ts::resolveDbBackend() exactly --
// same shape, same fail-closed philosophy, applied to artifact storage
// instead of the membership database. A hosted production deployment
// where the admin's Process/Refresh run and a member's read can be
// different machines MUST NOT silently read/write local disk (each
// process would see its own empty/unrelated filesystem) -- so production
// refuses to start with local storage unless an operator explicitly
// opts in via ALLOW_LOCAL_STORAGE_IN_PRODUCTION=true (e.g. a genuinely
// single-instance early deployment, mirroring ALLOW_SQLITE_IN_PRODUCTION).

export type StorageBackendKind = "local" | "object";

export interface StorageBackendDecision {
  kind: StorageBackendKind;
  reason: string;
}

export const ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG = "ALLOW_LOCAL_STORAGE_IN_PRODUCTION";

export class ProductionStorageNotConfiguredError extends Error {}

export function resolveStorageBackend(): StorageBackendDecision {
  const objectStorageConfig = resolveObjectStorageConfigFromEnv();
  if (objectStorageConfig) {
    return { kind: "object", reason: "OBJECT_STORAGE_* environment variables are configured." };
  }
  if (isProduction()) {
    if (process.env[ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG] === "true") {
      return {
        kind: "local",
        reason: `Object storage is not configured, but ${ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG}=true explicitly permits local disk in production.`,
      };
    }
    throw new ProductionStorageNotConfiguredError(
      "OBJECT_STORAGE_REGION, OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_ACCESS_KEY, and OBJECT_STORAGE_SECRET_KEY " +
        "are required in production (a shared object-storage bucket) -- refusing to silently fall back to local " +
        "disk, which would give separate app instances (and separate admin/member processes) disconnected, " +
        `unrelated artifact storage. Set the OBJECT_STORAGE_* variables, or explicitly set ${ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG}=true ` +
        "if you understand the risk (e.g. a genuinely single-instance early deployment).",
    );
  }
  return { kind: "local", reason: "No object storage configured; using local disk for development." };
}
