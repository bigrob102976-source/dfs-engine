import { getArtifactRoot } from "../artifactRoot";
import { LocalStorageBackend, ProductionObjectStorageBackend, type StorageBackend } from "./StorageBackend";
import { resolveStorageBackend } from "./backend";

let storageInstance: StorageBackend | null = null;

/** Milestone 33.2: THE single entry point every artifact reader in this
 * dashboard calls -- mirrors lib/db/executor.ts::getExecutor()'s exact
 * lazy-singleton, fail-closed-in-production shape, applied to artifact
 * storage instead of the membership database.
 *
 * Resolves the backend via resolveStorageBackend() (already implemented
 * in Milestone 30, previously unused) exactly once per process. When
 * OBJECT_STORAGE_* is configured, this ALWAYS returns a
 * ProductionObjectStorageBackend -- a broken bucket connection surfaces
 * as a rejected promise from whatever loader called it, never a silent
 * local-disk substitution. In production with no object storage
 * configured, resolveStorageBackend() itself throws
 * ProductionStorageNotConfiguredError (unless ALLOW_LOCAL_STORAGE_IN_PRODUCTION
 * is explicitly set) -- this function does not catch that; it is meant
 * to propagate. */
export function getStorage(): StorageBackend {
  if (!storageInstance) {
    const decision = resolveStorageBackend();
    storageInstance = decision.kind === "object" ? new ProductionObjectStorageBackend() : new LocalStorageBackend(getArtifactRoot());
  }
  return storageInstance;
}

/** Test-only: forces the next getStorage() call to rebuild from scratch.
 * Mirrors lib/db/executor.ts::__resetExecutorForTests(). */
export function __resetStorageForTests(): void {
  storageInstance = null;
}

/** Test-only: injects a pre-built backend directly (e.g. a
 * LocalStorageBackend rooted at a tmp dir, or a fake StorageBackend) so a
 * loader's business logic can be exercised without depending on
 * getArtifactRoot()/env resolution. */
export function __setStorageForTests(storage: StorageBackend): void {
  storageInstance = storage;
}
