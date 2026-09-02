import { afterEach, beforeEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { __resetStorageForTests } from "../../storage/getStorage";
import { LegacyR2ServingBackend } from "../legacyR2Backend";

// M5A -- thin-wrapper contract test: LegacyR2ServingBackend must be
// PROVABLY zero-behavior-change, i.e. it must just be poolCache.ts's
// existing listSlates/loadPool, not a reimplementation. Uses the exact
// same fixture convention as poolCache.test.ts.

let tmpDir: string;

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-legacybackend-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("../../optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("M5A: LegacyR2ServingBackend", () => {
  it("kind is LEGACY_R2", () => {
    expect(LegacyR2ServingBackend.kind).toBe("LEGACY_R2");
  });

  it("listSlates delegates to poolCache.ts's own listSlates, reusing an already-fetched legacy artifact", async () => {
    const date = "2026-08-31";
    writeJson(`dfs_input/${date}/provider_slate_0000000001.json`, {
      status: "ready", provider_name: "draftkings_unofficial", is_mock: false, source: "draftkings_unofficial_live",
      generated_at_utc: new Date().toISOString(), selected_slate_id: "dkunofficial-1",
      slates: [{ slate_id: "dkunofficial-1", slate_name: "Main", game_count: 8, start_time: null }],
      players: [],
    });

    const result = await LegacyR2ServingBackend.listSlates(date);
    expect(result.status).toBe("ready");
    expect(result.slates[0].slateId).toBe("dkunofficial-1");
  });
});
