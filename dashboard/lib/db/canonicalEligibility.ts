import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import { resolveMlbPlayerIds } from "./canonicalPlayerIdentity";
import { getExecutor } from "./executor";
import type { CanonicalSlatePlayerRow, CanonicalSlateRow } from "./types";

// M6A/M6B/M6C/M6D -- the Python<->Postgres eligibility bridge. Reuses
// dfs/eligibility.py::compute_eligibility() and dfs/slate_validation.py
// ::match_game_infos() UNCHANGED (M6 rules #11/#12), invoked as a
// subprocess (scripts/compute_canonical_eligibility.py) via the SAME
// runPythonScript() every other Python-spawning call in this codebase
// uses (see poolCache.ts). Python never touches Postgres directly (see
// canonical_ingestion/__init__.py's own documented reason) -- this
// module is the ONE place that reads canonical Postgres, builds the
// JSON payload the Python script expects, and persists its real results
// back onto slate_players' CURRENT state (never a new row, never
// touching immutable RAW/NORMALIZED artifacts -- M6E).

export interface EligibilityComputeResult {
  status: "OK" | "NO_RESEARCH_PACKAGE" | "SLATE_NOT_FOUND" | "ERROR";
  reason?: string;
  playersUpdated: number;
}

interface EligibilityPlayerResult {
  providerPlayerId: string;
  gameId: string | null;
  eligibilityStatus: string;
  optimizerEligible: boolean;
  battingOrder: number | null;
}

function parseJsonArray(json: string | null): string[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function parseResultJson(stdout: string): { status: string; reason?: string; results: EligibilityPlayerResult[] } | null {
  for (const line of stdout.split("\n").reverse()) {
    if (line.startsWith("RESULT_JSON:")) {
      try {
        return JSON.parse(line.slice("RESULT_JSON:".length));
      } catch {
        return null;
      }
    }
  }
  return null;
}

/** M6J: writes the eligibility-input payload to a unique file under the
 * OS temp directory (never a path derived from request input -- the
 * server always generates this path itself), invokes the real Python
 * bridge, and ALWAYS cleans up in a finally block, mirroring
 * buildRunner.ts's own writeProjectionOverridesFile/
 * cleanupProjectionOverridesFile convention exactly. */
export async function computeAndPersistEligibilityForSlate(internalSlateId: string): Promise<EligibilityComputeResult> {
  const db = getExecutor();
  const slate = await db.get<CanonicalSlateRow>("SELECT * FROM slates WHERE internal_slate_id = ?", [internalSlateId]);
  if (!slate) return { status: "SLATE_NOT_FOUND", playersUpdated: 0 };

  const playerRows = await db.all<CanonicalSlatePlayerRow>("SELECT * FROM slate_players WHERE internal_slate_id = ?", [internalSlateId]);
  const resolvedInternalPlayerIds = playerRows.map((p) => p.internal_player_id).filter((id): id is string => id !== null);
  const mlbIdByInternalPlayerId = await resolveMlbPlayerIds(resolvedInternalPlayerIds);

  const payload = {
    date: slate.slate_date,
    players: playerRows.map((p) => ({
      providerPlayerId: p.provider_player_id,
      name: p.name,
      team: p.team,
      opponent: p.opponent,
      positions: parseJsonArray(p.position_eligibility_json),
      salary: p.salary,
      identityStatus: p.identity_status,
      mlbPlayerId: p.internal_player_id ? (mlbIdByInternalPlayerId.get(p.internal_player_id) ?? null) : null,
    })),
  };

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-canonical-eligibility-"));
  const inputPath = path.join(dir, "players.json");
  try {
    fs.writeFileSync(inputPath, JSON.stringify(payload), "utf-8");

    const result = await runPythonScript("scripts/compute_canonical_eligibility.py", ["--date", slate.slate_date, "--input", inputPath]);
    const parsed = parseResultJson(result.stdout);
    if (!parsed) {
      return { status: "ERROR", reason: `Unexpected eligibility computation failure: ${tail(result.stdout + result.stderr, 1000)}`, playersUpdated: 0 };
    }
    if (parsed.status === "NO_RESEARCH_PACKAGE") {
      return { status: "NO_RESEARCH_PACKAGE", reason: parsed.reason, playersUpdated: 0 };
    }

    const now = new Date().toISOString();
    await db.transaction(async (tx) => {
      for (const r of parsed.results) {
        await tx.run(
          `UPDATE slate_players SET game_id = ?, eligibility_status = ?, optimizer_eligible = ?, batting_order = ?, eligibility_computed_at = ?, updated_at = ?
           WHERE internal_slate_id = ? AND provider_player_id = ?`,
          [r.gameId, r.eligibilityStatus, r.optimizerEligible ? 1 : 0, r.battingOrder, now, now, internalSlateId, r.providerPlayerId],
        );
      }
    });

    return { status: "OK", playersUpdated: parsed.results.length };
  } finally {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup of an OS temp file -- never fail eligibility computation over this.
    }
  }
}
