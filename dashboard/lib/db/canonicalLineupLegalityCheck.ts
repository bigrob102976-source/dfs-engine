import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import { getExecutor } from "./executor";
import type { CanonicalSlatePlayerRow } from "./types";

// M6L -- the honest, non-projection structural build proof: only
// OPTIMIZER-ELIGIBLE (real, persisted eligibility_status/
// optimizer_eligible from M6A-M6D -- never assumed) canonical players
// are ever passed to scripts/canonical_lineup_legality_check.py. This
// is READ-ONLY -- it never writes to slate_players or any other table;
// it exists purely to PROVE the bridge, not to persist anything.

export interface LineupLegalityCheckResult {
  status: "OK" | "SLATE_NOT_FOUND" | "ERROR";
  reason?: string;
  lineupsRequested: number;
  lineupsProduced: number;
  lineups: Array<Array<{ providerPlayerId: string; name: string; salary: number; positions: string[] }>>;
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

function parseResultJson(stdout: string): Record<string, unknown> | null {
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

export async function checkCanonicalLineupLegality(
  internalSlateId: string, options: { count?: number; salaryCap?: number; locks?: string[]; excludes?: string[] } = {},
): Promise<LineupLegalityCheckResult> {
  const db = getExecutor();
  const slate = await db.get<{ internal_slate_id: string; salary_cap: number | null }>(
    "SELECT internal_slate_id, salary_cap FROM slates WHERE internal_slate_id = ?", [internalSlateId],
  );
  if (!slate) return { status: "SLATE_NOT_FOUND", lineupsRequested: options.count ?? 1, lineupsProduced: 0, lineups: [] };

  const playerRows = await db.all<CanonicalSlatePlayerRow>(
    "SELECT * FROM slate_players WHERE internal_slate_id = ? AND optimizer_eligible = 1", [internalSlateId],
  );

  const payload = {
    count: options.count ?? 1,
    salaryCap: options.salaryCap ?? slate.salary_cap ?? 50000,
    locks: options.locks ?? [],
    excludes: options.excludes ?? [],
    players: playerRows.map((p) => ({
      providerPlayerId: p.provider_player_id, name: p.name, team: p.team,
      positions: parseJsonArray(p.position_eligibility_json), salary: p.salary,
    })),
  };

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-canonical-lineup-check-"));
  const inputPath = path.join(dir, "players.json");
  try {
    fs.writeFileSync(inputPath, JSON.stringify(payload), "utf-8");
    const result = await runPythonScript("scripts/canonical_lineup_legality_check.py", ["--input", inputPath]);
    const parsed = parseResultJson(result.stdout);
    if (!parsed) {
      return { status: "ERROR", reason: `Unexpected lineup legality check failure: ${tail(result.stdout + result.stderr, 1000)}`, lineupsRequested: payload.count, lineupsProduced: 0, lineups: [] };
    }
    return {
      status: "OK",
      lineupsRequested: parsed.lineupsRequested as number,
      lineupsProduced: parsed.lineupsProduced as number,
      lineups: parsed.lineups as LineupLegalityCheckResult["lineups"],
    };
  } finally {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup of an OS temp file.
    }
  }
}
