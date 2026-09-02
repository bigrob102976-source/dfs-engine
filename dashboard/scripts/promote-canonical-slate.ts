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
//
// M4M: --key may be repeated to promote SEVERAL artifacts in one
// process/one `railway ssh` round trip (scripts/fetch_dfs_slate.py's
// _run_canonical_promotion_batch) -- a live natural worker cycle showed
// several Classic slates for the same date (e.g. tomorrow's Main/Turbo/
// Night all needing promotion in the same ~5-minute cycle) paying
// repeated SSH connection-setup latency, once per slate, was enough to
// push total worker runtime past its own internal timeout. Each key is
// still promoted independently (its own transaction, its own result) --
// this only amortizes the SSH round trip, never batches the DB writes
// themselves:
//   npx tsx scripts/promote-canonical-slate.ts --key <key1> --key <key2> --key <key3>

import type { CanonicalSlateArtifactDocument } from "../lib/db/canonicalArtifact.ts";
import { promoteCanonicalArtifact } from "../lib/db/canonicalPromotion.ts";
import { getExecutor } from "../lib/db/executor.ts";
import { getStorage } from "../lib/storage/getStorage.ts";

export function parseArgs(argv: string[]): { keys: string[]; expectedHash?: string } {
  const keys: string[] = [];
  let expectedHash: string | undefined;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--key") {
      keys.push(argv[i + 1]);
      i += 1;
    } else if (argv[i] === "--expected-hash") {
      expectedHash = argv[i + 1];
      i += 1;
    }
  }
  if (keys.length === 0) {
    throw new Error("Usage: promote-canonical-slate.ts --key <normalized-artifact-key> [--key <key2> ...] [--expected-hash <normalizedHash>]");
  }
  return { keys, expectedHash };
}

async function main() {
  const { keys, expectedHash } = parseArgs(process.argv.slice(2));

  const storage = getStorage();
  const db = getExecutor();

  for (const key of keys) {
    console.log("=".repeat(70));
    console.log(`M2 CANONICAL PROMOTION -- ${key}`);
    console.log("=".repeat(70));

    const artifact = await storage.readJson<CanonicalSlateArtifactDocument>(key);
    if (!artifact) {
      console.error(`No NORMALIZED artifact found at key: ${key}`);
      process.exitCode = 1;
      console.log(`RESULT_JSON:${JSON.stringify({ promoted: false, reason: `No NORMALIZED artifact found at key: ${key}` })}`);
      continue;
    }

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
    // legitimate no-op/rejection outcome). One such line per --key,
    // always in the same order they were given (M4M batch mode).
    console.log(`RESULT_JSON:${JSON.stringify(result)}`);
  }
}

main().catch((err) => {
  console.error("Canonical promotion failed:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
