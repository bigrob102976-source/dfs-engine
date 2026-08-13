import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-12";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-artifactstatus-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("getArtifactStatus", () => {
  it("everything is missing when no artifacts exist", async () => {
    const { getArtifactStatus } = await import("../artifactStatus");
    expect(getArtifactStatus(DATE)).toEqual({
      research: false,
      pitchers: false,
      batters: false,
      dfsSalaries: false,
      playerPool: false,
      ownership: false,
      optimizer: false,
    });
  });

  it("marks research/pitchers/batters ready as soon as their files exist", async () => {
    writeJson(`research_output/${DATE}/slate.json`, { slate_date: DATE });
    writeJson(`predictions/${DATE}/pitcher_board_0000000001.json`, {});
    writeJson(`predictions/${DATE}/batter_board_0000000001.json`, {});

    const { getArtifactStatus } = await import("../artifactStatus");
    const status = getArtifactStatus(DATE);
    expect(status.research).toBe(true);
    expect(status.pitchers).toBe(true);
    expect(status.batters).toBe(true);
    expect(status.playerPool).toBe(false);
  });

  it("dfsSalaries is only ready when the latest provider slate has status 'ready'", async () => {
    writeJson(`dfs_input/${DATE}/provider_slate_0000000001.json`, { status: "needs_selection" });
    const { getArtifactStatus } = await import("../artifactStatus");
    expect(getArtifactStatus(DATE).dfsSalaries).toBe(false);

    writeJson(`dfs_input/${DATE}/provider_slate_0000000002.json`, { status: "ready" });
    const status = getArtifactStatus(DATE);
    expect(status.dfsSalaries).toBe(true);
  });

  it("playerPool is only ready when the pool file exists AND roster_feasibility_pass is true", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000001.json`, { roster_feasibility_pass: false });
    const { getArtifactStatus } = await import("../artifactStatus");
    expect(getArtifactStatus(DATE).playerPool).toBe(false);

    writeJson(`dfs_input/${DATE}/dk_player_pool_0000000002.json`, { roster_feasibility_pass: true });
    expect(getArtifactStatus(DATE).playerPool).toBe(true);
  });

  it("ownership and optimizer are ready as soon as any snapshot/lineup set exists", async () => {
    writeJson(`ownership_predictions/${DATE}/ownership_0000000001.json`, {});
    writeJson(`lineups/${DATE}/dk_lineups_0000000001.json`, {});
    const { getArtifactStatus } = await import("../artifactStatus");
    const status = getArtifactStatus(DATE);
    expect(status.ownership).toBe(true);
    expect(status.optimizer).toBe(true);
  });

  it("is a pure read -- calling it never creates or modifies any file", async () => {
    const { getArtifactStatus } = await import("../artifactStatus");
    getArtifactStatus(DATE);
    expect(fs.existsSync(path.join(tmpDir, "research_output"))).toBe(false);
  });
});
