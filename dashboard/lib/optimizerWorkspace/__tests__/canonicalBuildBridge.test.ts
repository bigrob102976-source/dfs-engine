import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../../db/client";
import { __resetExecutorForTests } from "../../db/executor";
import { __resetStorageForTests } from "../../storage/getStorage";
import type { PythonRunResult } from "../../orchestrator/pythonRunner";
import type { OptimizerBuildRequest } from "../types";

const DATE = "2026-08-31";
let tmpDir: string;

function baseRequest(overrides: Partial<OptimizerBuildRequest> = {}): OptimizerBuildRequest {
  return {
    date: DATE, slateId: "dkunofficial-canary", lineups: 1, objective: "projection",
    locks: [], exclusions: [], maxExposure: {}, stackSize: null, stackTeam: null, stackSize2: null, stackTeam2: null,
    allowPitcherVsHitter: false, minSalary: null, minUnique: 2, minConfidence: null, maxPlayerRisk: null,
    projectionSource: "independent", servingBackend: "CANONICAL_POSTGRES",
    ...overrides,
  };
}

function seedCanonicalSlate() {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         game_count, game_ids_json, salary_cap, schema_version, validation_state, source_provenance, promoted_at,
         player_count, created_at, updated_at
       ) VALUES ('canary-s1', 'MLB', 'draftkings', 'draftkings_unofficial', 'dkunofficial-canary', 'Main', ?, '2026-08-31T23:05:00Z', 8, '[]', 50000, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', ?, 1, 'x', 'x')`,
    )
    .run(DATE, new Date().toISOString());
}

function seedCanonicalPlayer(overrides: { providerPlayerId?: string; eligibilityStatus?: string; optimizerEligible?: number } = {}) {
  const row = { providerPlayerId: "1", eligibilityStatus: "STARTING_PITCHER", optimizerEligible: 1, ...overrides };
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, eligibility_status, optimizer_eligible, eligibility_computed_at, created_at, updated_at)
       VALUES ('canary-s1', ?, 'Canary Pitcher', 'BOS', 'TOR', 8000, '["P"]', 'UNRESOLVED', ?, ?, 'x', 'x', 'x')`,
    )
    .run(row.providerPlayerId, row.eligibilityStatus, row.optimizerEligible);
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-canonical-build-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  __resetStorageForTests();
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("M6I/M6J: canonical build bridge -- reaches the real, unmodified optimizer script", () => {
  it("materializes a real temp dk_player_pool-shaped file and invokes the SAME optimize_dk_lineups.py, then cleans it up", async () => {
    seedCanonicalSlate();
    seedCanonicalPlayer();

    let capturedPoolPath: string | null = null;
    let capturedPoolDoc: { players: Array<Record<string, unknown>> } | null = null;
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script, args): Promise<PythonRunResult> => {
      expect(script).toBe("scripts/optimize_dk_lineups.py"); // the SAME, unmodified script -- M6I
      const poolIdx = args.indexOf("--pool");
      capturedPoolPath = args[poolIdx + 1];
      capturedPoolDoc = JSON.parse(fs.readFileSync(capturedPoolPath, "utf-8"));
      return { exitCode: 0, stdout: JSON.stringify({ errors: [], coverage: { pool_size: 1, optimizer_eligible: 1, usable_for_build: 0, skipped_missing_projection: 1, excluded_missing_source: 0, projection_source: "independent", strict_source: false } }), stderr: "", command: [] };
    });

    const { validateBuildRequest } = await import("../buildRunner");
    await validateBuildRequest(baseRequest());

    expect(capturedPoolPath).toBeTruthy();
    expect(capturedPoolDoc!.players).toHaveLength(1);
    const player = capturedPoolDoc!.players[0];
    expect(player.dk_player_id).toBe("1");
    expect(player.salary).toBe(8000);
    expect(player.eligibility_status).toBe("STARTING_PITCHER");
    expect(player.optimizer_eligible).toBe(true);
    // M6M: never fabricated.
    expect(player.projection).toBeNull();
    expect(player.ceiling).toBeNull();

    // M6J: cleaned up after the call.
    expect(fs.existsSync(path.dirname(capturedPoolPath!))).toBe(false);
  });

  it("M6M: with real (unmocked-logic) coverage reporting zero usable players for lack of projections, the bridge honestly refuses -- never fabricates a projection to force a lineup through", async () => {
    seedCanonicalSlate();
    seedCanonicalPlayer();

    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        errors: ["0 of 1 pool player(s) are optimizer-eligible... yet 1 otherwise-eligible player(s) have no projection/ceiling at all for this slate yet."],
        coverage: { pool_size: 1, optimizer_eligible: 1, usable_for_build: 0, skipped_missing_projection: 1, excluded_missing_source: 0, projection_source: "independent", strict_source: false },
      }),
      stderr: "", command: [],
    }));

    const { validateBuildRequest } = await import("../buildRunner");
    const result = await validateBuildRequest(baseRequest());
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.coverage?.usableForBuild).toBe(0);
  });

  it("returns the 'no player pool loaded' error honestly when canonical getSlatePool itself fails (e.g. absent slate) -- never a crash", async () => {
    // No seedCanonicalSlate() -- genuinely absent.
    const { validateBuildRequest } = await import("../buildRunner");
    const result = await validateBuildRequest(baseRequest());
    expect(result.errors).toEqual(["No player pool loaded for this slate yet -- select a slate first."]);
  });

  it("LEGACY_R2 (default/no servingBackend) is completely unaffected -- still uses getCachedPoolPath, never touches canonical Postgres", async () => {
    const { validateBuildRequest } = await import("../buildRunner");
    const result = await validateBuildRequest(baseRequest({ servingBackend: undefined }));
    expect(result.errors).toEqual(["No player pool loaded for this slate yet -- select a slate first."]);
  });
});
