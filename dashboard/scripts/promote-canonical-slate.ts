// M2G -- reads one NORMALIZED R2 artifact (written by Python's
// canonical_ingestion/normalized_storage.py) and promotes it into the
// canonical Postgres shadow-CURRENT tables via
// lib/db/canonicalPromotion.ts::promoteCanonicalArtifact -- the SAME
// function dashboard/scripts/rehydrate-canonical-current.ts (M2J) uses,
// so promotion and rehydration are provably one operation, never two
// divergent implementations.
//
// SHADOW ONLY: never touches slate_status, poolCache.ts, or any
// customer-facing table/route. Uses getExecutor() (lib/db/executor.ts),
// which resolves Postgres automatically when DATABASE_URL is set
// (production/CI) or SQLite otherwise (local dev) -- same convention as
// every other script in this project (see scripts/run-job-worker.ts).
//
// Usage (from dashboard/, via tsx -- see package.json's "db:migrate:postgres"
// for why plain `node` doesn't work for this project's extensionless
// internal imports):
//   npx tsx scripts/promote-canonical-slate.ts --key normalized/MLB/2026-08-31/draftkings_unofficial/152904/20260831T200000000000.json
//   npx tsx scripts/promote-canonical-slate.ts --key <...> --expected-hash <normalizedHash>

import type { CanonicalSlateArtifactDocument } from "../lib/db/canonicalArtifact.ts";
import { promoteCanonicalArtifact } from "../lib/db/canonicalPromotion.ts";
import { getExecutor } from "../lib/db/executor.ts";
import { getStorage } from "../lib/storage/getStorage.ts";

function parseArgs(argv: string[]): { key: string; expectedHash?: string } {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i].startsWith("--")) {
      args[argv[i].slice(2)] = argv[i + 1];
      i += 1;
    }
  }
  if (!args.key) {
    throw new Error("Usage: promote-canonical-slate.ts --key <normalized-artifact-key> [--expected-hash <normalizedHash>]");
  }
  return { key: args.key, expectedHash: args["expected-hash"] };
}

async function main() {
  const { key, expectedHash } = parseArgs(process.argv.slice(2));

  console.log("=".repeat(70));
  console.log(`M2 CANONICAL PROMOTION -- ${key}`);
  console.log("=".repeat(70));

  const storage = getStorage();
  const artifact = await storage.readJson<CanonicalSlateArtifactDocument>(key);
  if (!artifact) {
    console.error(`No NORMALIZED artifact found at key: ${key}`);
    process.exitCode = 1;
    return;
  }

  const db = getExecutor();
  const result = await promoteCanonicalArtifact(db, artifact, {
    normalizedArtifactPath: key,
    rawArtifactPath: null,
    expectedNormalizedHash: expectedHash,
  });

  console.log(JSON.stringify(result, null, 2));
  if (result.promoted) {
    console.log(`\nPROMOTED -- internalSlateId=${result.internalSlateId}, reviewQueueEntriesCreated=${result.reviewQueueEntriesCreated ?? 0}`);
  } else {
    console.log(`\nNOT PROMOTED -- ${result.reason}`);
  }
  // M3K: a single, compact, uniquely-prefixed line a calling process
  // (scripts/fetch_dfs_slate.py) can parse without needing to locate a
  // multi-line pretty-printed JSON block inside captured stdout -- used
  // to gate the M3K success heartbeat on `promoted === true` specifically
  // (not merely "this script exited 0", which is also true for a
  // legitimate no-op/rejection outcome).
  console.log(`RESULT_JSON:${JSON.stringify(result)}`);
}

main().catch((err) => {
  console.error("Canonical promotion failed:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
