import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetStorageForTests } from "../storage/getStorage";

let tmpDir: string;

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-loaders-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  // getStorage() is a lazy singleton (mirrors lib/db/executor.ts::getExecutor())
  // cached at module scope -- without this reset, a getArtifactRoot()
  // resolved from an EARLIER test's MLB_DFS_ROOT value would stay
  // cached and this test would silently read/write against a directory
  // that no longer exists.
  __resetStorageForTests();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

const DATE = "2026-08-17";

describe("loadLatestDKPlayerPool (Milestone 26 slate-aware resolution)", () => {
  it("falls back to plain 'latest file' behavior when no slateId is given", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000001.json`, { selected_slate_id: "main", player_count: 1, players: [] });
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000002.json`, { selected_slate_id: "turbo", player_count: 2, players: [] });

    const { loadLatestDKPlayerPool } = await import("../loaders");
    const result = await loadLatestDKPlayerPool(DATE);
    expect(result.data?.selected_slate_id).toBe("turbo"); // most recently written file, regardless of slate
  });

  it("resolves the LATEST pool matching the given slateId, ignoring a more recent OTHER slate's pool", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000001.json`, { selected_slate_id: "main", player_count: 1, players: [] });
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000002.json`, { selected_slate_id: "turbo", player_count: 2, players: [] });
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000003.json`, { selected_slate_id: "main", player_count: 3, players: [] });

    const { loadLatestDKPlayerPool } = await import("../loaders");
    const mainResult = await loadLatestDKPlayerPool(DATE, "main");
    expect(mainResult.data?.player_count).toBe(3); // the newer of the two Main pools, not Turbo's

    const turboResult = await loadLatestDKPlayerPool(DATE, "turbo");
    expect(turboResult.data?.player_count).toBe(2);
  });

  it("returns null data (never another slate's pool) when the requested slateId was never built", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000001.json`, { selected_slate_id: "main", player_count: 1, players: [] });

    const { loadLatestDKPlayerPool } = await import("../loaders");
    const result = await loadLatestDKPlayerPool(DATE, "night");
    expect(result.data).toBeNull();
  });
});

describe("loadLatestDkMatchReport (Milestone 26 slate-aware resolution)", () => {
  it("resolves the match report sharing its slate-matched pool's exact timestamp", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000001.json`, { selected_slate_id: "main", player_count: 1, players: [] });
    writeJson(`dfs_input/${DATE}/dk_match_report_0000000001.json`, { dk_games_total: 9, slate_marker: "main-report" });
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000002.json`, { selected_slate_id: "turbo", player_count: 2, players: [] });
    writeJson(`dfs_input/${DATE}/dk_match_report_0000000002.json`, { dk_games_total: 3, slate_marker: "turbo-report" });

    const { loadLatestDkMatchReport } = await import("../loaders");
    const mainReport = await loadLatestDkMatchReport(DATE, "main");
    expect(mainReport.data?.slate_marker).toBe("main-report");
    expect(mainReport.data?.dk_games_total).toBe(9);

    const turboReport = await loadLatestDkMatchReport(DATE, "turbo");
    expect(turboReport.data?.slate_marker).toBe("turbo-report");
  });

  it("returns null data when the requested slate has no matching pool at all", async () => {
    const { loadLatestDkMatchReport } = await import("../loaders");
    const result = await loadLatestDkMatchReport(DATE, "night");
    expect(result.data).toBeNull();
  });
});
