import type { StorageBackend } from "./StorageBackend";

// Milestone 33.5: cross-language half of the production object-storage
// smoke test. scripts/smoke_test_object_storage.py (Python) does the
// full write/head/read/verify/delete round trip -- Node's own
// StorageBackend abstraction has no write capability by design
// (lib/artifactRoot.ts: "this dashboard never writes into this tree --
// it only reads", Milestone 33.2), so this is deliberately read-only.
// Meant to run AFTER `python scripts/smoke_test_object_storage.py
// --no-cleanup` has written the object and BEFORE its paired
// `--cleanup-only` run deletes it, proving the Node/WEB side can read
// the exact same real bucket the Python/WORKER side just wrote to --
// the concrete form of "WEB and WORKER share the same object-storage
// namespace." See dashboard/scripts/smoke-test-object-storage-read.ts
// for the CLI entry point that calls this.

export const DEFAULT_OBJECT_STORAGE_SMOKE_TEST_KEY = "healthchecks/r2-smoke-test.txt";

export interface ObjectStorageReadCheckResult {
  exists: boolean;
  readable: boolean;
  contentLooksValid: boolean;
  allOk: boolean;
}

export async function runObjectStorageReadCheck(storage: StorageBackend, key: string): Promise<ObjectStorageReadCheckResult> {
  const exists = await storage.exists(key);
  const content = await storage.readJson<{ smoke_test?: boolean; source?: string }>(key);
  const readable = content !== null;
  const contentLooksValid = Boolean(content && content.smoke_test === true);
  return { exists, readable, contentLooksValid, allOk: exists && contentLooksValid };
}
