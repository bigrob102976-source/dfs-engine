// M2J -- rehydration foundation: rebuilds the canonical Postgres
// shadow-CURRENT slate/slate_players rows from a stored, immutable
// NORMALIZED R2 artifact. This is deliberately the EXACT SAME operation
// as scripts/promote-canonical-slate.ts (both call
// lib/db/canonicalPromotion.ts::promoteCanonicalArtifact) -- rehydration
// is not a separate, divergent code path; it is "promotion, triggered
// by an operator instead of live ingestion."
//
// Every M2J requirement is already enforced inside promoteCanonicalArtifact:
//   - schemaVersion checked (unknown version -> refused)
//   - validation required (validationState must be VALID)
//   - transactional (one db.transaction() call)
//   - no fuzzy identity guesses (identity was already decided by
//     canonical_ingestion/identity_bridge.py; this never re-decides)
//   - unresolved identity allowed (nullable internal_player_id)
//   - an older artifact cannot silently overwrite a newer CURRENT
//     UNLESS --force is passed
//
// --force is the one thing THIS script adds beyond ordinary promotion:
// an explicit, operator-only override (never automatic, never callable
// from any customer-facing or scheduled path) that skips the
// older-artifact/no-op guards -- e.g. to deliberately restore CURRENT
// from an old R2 artifact after discovering a bad live promotion.
//
// This tool does NOT affect the legacy customer path in M2 -- it only
// ever writes to the canonical shadow tables (players, player_external_ids,
// slates, slate_players, identity_review_queue).
//
// Usage:
//   npx tsx scripts/rehydrate-canonical-current.ts --key <normalized-artifact-key>
//   npx tsx scripts/rehydrate-canonical-current.ts --key <...> --expected-hash <hash> --force

import type { CanonicalSlateArtifactDocument } from "../lib/db/canonicalArtifact.ts";
import { promoteCanonicalArtifact } from "../lib/db/canonicalPromotion.ts";
import { getExecutor } from "../lib/db/executor.ts";
import { getStorage } from "../lib/storage/getStorage.ts";

function parseArgs(argv: string[]): { key: string; expectedHash?: string; force: boolean } {
  const args: Record<string, string> = {};
  let force = false;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--force") {
      force = true;
      continue;
    }
    if (argv[i].startsWith("--")) {
      args[argv[i].slice(2)] = argv[i + 1];
      i += 1;
    }
  }
  if (!args.key) {
    throw new Error("Usage: rehydrate-canonical-current.ts --key <normalized-artifact-key> [--expected-hash <hash>] [--force]");
  }
  return { key: args.key, expectedHash: args["expected-hash"], force };
}

async function main() {
  const { key, expectedHash, force } = parseArgs(process.argv.slice(2));

  console.log("=".repeat(70));
  console.log(`M2J CANONICAL REHYDRATION -- ${key}${force ? " (--force)" : ""}`);
  console.log("=".repeat(70));
  if (force) {
    console.log("WARNING: --force is set -- this will override the older-artifact and no-op guards. Operator-only; never run this automatically.");
  }

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
    force,
  });

  console.log(JSON.stringify(result, null, 2));
  if (result.promoted) {
    console.log(`\nREHYDRATED -- internalSlateId=${result.internalSlateId}`);
  } else {
    console.log(`\nNOT REHYDRATED -- ${result.reason}`);
  }
}

main().catch((err) => {
  console.error("Canonical rehydration failed:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
