import crypto from "node:crypto";

import { loadLatestOwnershipSnapshot } from "../loaders";
import { cleanupCanonicalPoolFile, materializeCanonicalPoolFile } from "../optimizerWorkspace/canonicalPoolMaterialization";
import type { OptimizerPoolResult } from "../optimizerWorkspace/types";
import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import { getExecutor } from "./executor";
import type { CanonicalSlateRow } from "./types";

// MLB FINISH MODE Phase D -- the ownership bridge. Reuses
// scripts/project_dk_ownership.py / ownership/*.py COMPLETELY
// UNCHANGED -- that script has always required a real DK-pool-shaped
// JSON file with real salary/position/eligibility/projection/ceiling
// fields (its own real input gate: a player without BOTH `projection`
// and `ceiling` is silently excluded, never assigned a fake 0 -- see
// that script's own docstring). canonicalPoolMaterialization.ts (M6J,
// extended by this milestone's Phase B) already produces exactly that
// shape from a real canonical pool; this module's only job is to run
// that real script against it and persist the REAL, immutable artifact
// it writes back onto this slate's CURRENT ownership state.
//
// Deliberately takes an ALREADY-BUILT `pool` (OptimizerPoolResult)
// rather than building one itself -- canonicalGetSlatePool() (which
// builds that pool) lives in canonicalPostgresBackend.ts, and that file
// only ever needs to READ this module's getCanonicalOwnershipForSlate()
// (never this module's write path), so passing the pool in as a
// parameter avoids a circular import between the two files entirely.
// The caller (the automatic orchestration script) already has the pool
// in hand from running Phase B's projection refresh moments earlier.

export interface OwnershipComputeResult {
  status: "OK" | "NO_USABLE_PLAYERS" | "SLATE_NOT_FOUND" | "ERROR";
  reason?: string;
  playersUpdated: number;
}

export async function computeAndPersistOwnershipForSlate(internalSlateId: string, pool: OptimizerPoolResult): Promise<OwnershipComputeResult> {
  const db = getExecutor();
  const slate = await db.get<CanonicalSlateRow>("SELECT * FROM slates WHERE internal_slate_id = ?", [internalSlateId]);
  if (!slate) return { status: "SLATE_NOT_FOUND", playersUpdated: 0 };

  // Mirrors project_dk_ownership.py's own real input gate exactly (see
  // that script's _build_input_players()) -- checked here first only so
  // this bridge can report an honest, specific reason instead of a
  // generic "the script ran but produced nothing" when the real cause is
  // simply "no usable projections exist for this slate yet" (e.g. Phase
  // B hasn't run for it, or the Native engine has zero coverage today).
  const usablePlayers = pool.players.filter((p) => p.optimizerEligible && p.projection !== null && p.ceiling !== null);
  if (usablePlayers.length === 0) {
    return { status: "NO_USABLE_PLAYERS", reason: "No optimizer-eligible player currently has both a real projection and ceiling.", playersUpdated: 0 };
  }

  const poolFilePath = materializeCanonicalPoolFile(pool);
  try {
    const result = await runPythonScript("scripts/project_dk_ownership.py", [
      "--date", slate.slate_date, "--pool", poolFilePath, "--slate-id", slate.provider_slate_id,
    ]);
    if (result.exitCode !== 0) {
      return { status: "ERROR", reason: tail(result.stdout + result.stderr, 1000), playersUpdated: 0 };
    }

    // Read back the REAL, immutable artifact the script just wrote --
    // never parse stdout for the actual per-player data.
    const loaded = await loadLatestOwnershipSnapshot(slate.slate_date, slate.provider_slate_id);
    if (!loaded.data) {
      return { status: "ERROR", reason: "project_dk_ownership.py exited 0 but no ownership snapshot was found afterward.", playersUpdated: 0 };
    }
    const snapshot = loaded.data;

    const now = new Date().toISOString();
    let playersUpdated = 0;
    await db.transaction(async (tx) => {
      for (const p of snapshot.players) {
        await tx.run(
          `INSERT INTO canonical_slate_player_ownership
             (id, internal_slate_id, provider_player_id, model_version, projected_ownership, ownership_tier, leverage_score, chalk_score, generated_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (internal_slate_id, provider_player_id) DO UPDATE SET
             model_version = excluded.model_version, projected_ownership = excluded.projected_ownership,
             ownership_tier = excluded.ownership_tier, leverage_score = excluded.leverage_score, chalk_score = excluded.chalk_score,
             generated_at = excluded.generated_at, updated_at = excluded.updated_at`,
          [
            crypto.randomUUID(), internalSlateId, p.dk_player_id, snapshot.model_version, p.projected_ownership,
            p.ownership_tier, p.leverage_score, p.chalk_score, snapshot.generated_at ?? null, now, now,
          ],
        );
        playersUpdated += 1;
      }
    });

    return { status: "OK", playersUpdated };
  } finally {
    cleanupCanonicalPoolFile(poolFilePath);
  }
}

export interface CanonicalOwnershipRow {
  provider_player_id: string;
  model_version: string | null;
  projected_ownership: number | null;
  ownership_tier: string | null;
  leverage_score: number | null;
  chalk_score: number | null;
  generated_at: string | null;
}

/** Read-only: every persisted ownership row for a slate, keyed by
 * provider_player_id (DK id) -- same key convention as every other
 * per-player canonical join. */
export async function getCanonicalOwnershipForSlate(internalSlateId: string): Promise<Map<string, CanonicalOwnershipRow>> {
  const db = getExecutor();
  const rows = await db.all<CanonicalOwnershipRow>(
    "SELECT provider_player_id, model_version, projected_ownership, ownership_tier, leverage_score, chalk_score, generated_at FROM canonical_slate_player_ownership WHERE internal_slate_id = ?",
    [internalSlateId],
  );
  return new Map(rows.map((r) => [r.provider_player_id, r]));
}
