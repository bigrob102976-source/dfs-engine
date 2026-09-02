import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../../db/client";
import { __resetExecutorForTests } from "../../db/executor";
import { __resetStorageForTests } from "../../storage/getStorage";

/** M4I -- explicit customer-isolation proof. M4's whole premise is that
 * canonical Postgres can now hold a REAL, fully-promoted row for
 * TOMORROW's date (scripts/fetch_all_dfs_slates.py::prefetch_future_
 * slates) while customer-facing MLB keeps reading ONLY the legacy R2
 * path (poolCache.ts). This file proves that structurally AND
 * behaviorally -- a future canonical row existing must never change
 * what a customer-facing read returns for today. */

const TODAY = "2026-09-01";
const TOMORROW_CANONICAL_INTERNAL_SLATE_ID = "tomorrow-canonical-1";

let tmpDir: string;

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-isolation-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

/** Seeds a REAL, fully-promoted canonical Postgres row for TOMORROW --
 * exactly what a natural worker cycle's prefetch_future_slates() step
 * would have written via promoteCanonicalArtifact(). */
function seedTomorrowCanonicalSlate() {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         schema_version, validation_state, player_count, resolved_identity_count, unresolved_identity_count,
         review_required_count, is_semantic_duplicate, created_at, updated_at
       ) VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', '999999', 'Main', '2026-09-02', '2026-09-02T23:05:00Z',
         'slate_normalized_v1', 'VALID', 1, 0, 1, 0, 0, 'x', 'x')`,
    )
    .run(TOMORROW_CANONICAL_INTERNAL_SLATE_ID);
}

function seedTodayLegacyArtifact() {
  writeJson(`dfs_input/${TODAY}/provider_slate_0000000001.json`, {
    status: "ready",
    provider_name: "draftkings_unofficial",
    provider_type: "draftkings_unofficial",
    is_mock: false,
    source: "draftkings_unofficial_live",
    generated_at_utc: new Date().toISOString(),
    selected_slate_id: "dkunofficial-today-1",
    slates: [{ slate_id: "dkunofficial-today-1", slate_name: "Main", game_count: 12, start_time: null }],
    players: [],
  });
}

describe("M4I: tomorrow's canonical prefetch never leaks into customer-facing reads", () => {
  it("poolCache.ts never imports any canonical Postgres module (structural isolation)", () => {
    const src = fs.readFileSync(path.join(__dirname, "..", "poolCache.ts"), "utf8");
    for (const forbidden of ["canonicalPromotion", "canonicalShadowStatus", "lib/db/executor", "lib/db/client", "getExecutor"]) {
      expect(src).not.toContain(forbidden);
    }
  });

  it("today's customer slate list is unaffected by a real canonical row existing for tomorrow", async () => {
    seedTomorrowCanonicalSlate();
    seedTodayLegacyArtifact();

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(TODAY);

    expect(result.status).toBe("ready");
    expect(result.slates).toEqual([
      { slateId: "dkunofficial-today-1", slateName: "Main", gameCount: 12, startTime: null, gameIds: [], playerCount: null },
    ]);
    // Nothing from tomorrow's canonical row (its providerSlateId, its
    // internalSlateId, its own slate_id) ever appears in a customer read.
    const serialized = JSON.stringify(result);
    expect(serialized).not.toContain("999999");
    expect(serialized).not.toContain(TOMORROW_CANONICAL_INTERNAL_SLATE_ID);
  });

  it("today's customer slate list is identical whether or not tomorrow has been canonically prefetched", async () => {
    seedTodayLegacyArtifact();
    const { listSlates, __resetPoolCacheForTests } = await import("../poolCache");
    const withoutTomorrow = await listSlates(TODAY);

    __resetPoolCacheForTests();
    seedTomorrowCanonicalSlate();
    const withTomorrow = await listSlates(TODAY);

    expect(withTomorrow).toEqual(withoutTomorrow);
  });

  it("a future canonical row for tomorrow does not appear when a customer asks for TODAY's date with no legacy artifact yet", async () => {
    seedTomorrowCanonicalSlate();
    // No legacy artifact for today at all -- listSlates must fall through
    // to its own live-discovery handling, never substitute tomorrow's
    // canonical (Postgres) data for today's missing legacy artifact.
    const { __setPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "not_connected", reason: "no provider configured", provider_name: null, provider_type: null,
        is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
      }),
      stderr: "", command: [],
    }));

    const { listSlates } = await import("../poolCache");
    const result = await listSlates(TODAY);
    expect(result.slates).toEqual([]);
    expect(JSON.stringify(result)).not.toContain("999999");
  });
});
