// Milestone 33.5: CLI entry point for the Node-side half of the
// production object-storage smoke test -- see
// lib/storage/objectStorageReadCheck.ts for the actual (independently
// tested) logic this just wraps and reports.
//
// Usage (from dashboard/, in an environment where OBJECT_STORAGE_* is
// already configured):
//   npx tsx scripts/smoke-test-object-storage-read.ts [key]
//
// Prints one sanitized JSON report; never a credential value. Uses
// ONLY the existing getStorage()/resolveStorageBackend() abstraction,
// never a direct @aws-sdk/client-s3 call -- exactly the same code path
// every real Node-side artifact read already goes through.

import { resolveStorageBackend } from "../lib/storage/backend";
import { getStorage } from "../lib/storage/getStorage";
import { DEFAULT_OBJECT_STORAGE_SMOKE_TEST_KEY, runObjectStorageReadCheck } from "../lib/storage/objectStorageReadCheck";

async function main() {
  const key = process.argv[2] || DEFAULT_OBJECT_STORAGE_SMOKE_TEST_KEY;
  const report: Record<string, unknown> = { key };

  const decision = resolveStorageBackend();
  report.backendResolved = decision.kind;

  if (decision.kind !== "object") {
    report.error =
      "resolveStorageBackend() resolved to local disk, not object storage -- OBJECT_STORAGE_* is not fully configured in this environment.";
    console.log(JSON.stringify(report, null, 2));
    process.exit(1);
  }

  const result = await runObjectStorageReadCheck(getStorage(), key);
  Object.assign(report, result);
  console.log(JSON.stringify(report, null, 2));
  process.exit(result.allOk ? 0 : 1);
}

main();
