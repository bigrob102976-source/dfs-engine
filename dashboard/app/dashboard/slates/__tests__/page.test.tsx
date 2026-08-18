import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function writeJson(root: string, relPath: string, data: unknown) {
  const filePath = path.join(root, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

const DATE = "2026-08-17";
let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-slate-manager-page-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({})));
  vi.doMock("@/lib/currentDate", () => ({ getTodayChicagoDate: () => DATE }));
});

afterEach(() => {
  vi.doUnmock("@/lib/currentDate");
  vi.resetModules();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  fs.rmSync(tmpDir, { recursive: true, force: true });
  delete process.env.MLB_DFS_ROOT;
});

async function stubSlates(slates: unknown[], providerName: string | null = "draftkings_csv", isMock = false) {
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async (script: string) => {
    if (script === "scripts/list_dfs_slates.py") {
      return {
        exitCode: 0,
        stdout: JSON.stringify({
          status: slates.length ? "ready" : "not_connected", reason: null, provider_name: providerName,
          provider_type: isMock ? "mock" : "real", is_mock: isMock, is_connected: slates.length > 0,
          source: isMock ? "mock_explicit" : "real_dk_csv", slates, slates_available: slates.length,
        }),
        stderr: "",
        command: [],
      };
    }
    throw new Error(`Unexpected script call: ${script}`);
  });
}

describe("SlateManagerPage", () => {
  it("shows the empty state when no slates are discovered", async () => {
    await stubSlates([], null, false);
    const SlateManagerPage = (await import("../page")).default;
    render(await SlateManagerPage());
    expect(screen.getByText(/No slates discovered yet/)).toBeInTheDocument();
  });

  it("marks a slate READY only when both its pool and ownership snapshot exist", async () => {
    await stubSlates([
      { slate_id: "main", slate_name: "Main", game_count: 9, start_time: null, game_ids: ["g1"], player_count: 142 },
      { slate_id: "turbo", slate_name: "Turbo", game_count: 3, start_time: null, game_ids: ["g2"], player_count: 58 },
    ]);

    writeJson(tmpDir, `dfs_input/${DATE}/dk_player_pool_0000000001.json`, { selected_slate_id: "main", player_count: 142, players: [] });
    writeJson(tmpDir, `dfs_input/${DATE}/dk_match_report_0000000001.json`, {});
    writeJson(tmpDir, `ownership_predictions/${DATE}/main/ownership_0000000001.json`, { slate_id: "main", players: [] });
    // Turbo has a pool but no ownership yet -- PARTIAL, not READY.
    writeJson(tmpDir, `dfs_input/${DATE}/dk_player_pool_0000000002.json`, { selected_slate_id: "turbo", player_count: 58, players: [] });
    writeJson(tmpDir, `dfs_input/${DATE}/dk_match_report_0000000002.json`, {});

    const SlateManagerPage = (await import("../page")).default;
    render(await SlateManagerPage());

    expect(screen.getByText("Main")).toBeInTheDocument();
    expect(screen.getByText("Turbo")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByText("PARTIAL")).toBeInTheDocument();
  });

  it("marks a slate MISSING when neither its pool nor ownership exists yet", async () => {
    await stubSlates([{ slate_id: "night", slate_name: "Night", game_count: 5, start_time: null, game_ids: ["g3"], player_count: 82 }]);

    const SlateManagerPage = (await import("../page")).default;
    render(await SlateManagerPage());

    expect(screen.getByText("Night")).toBeInTheDocument();
    expect(screen.getByText("MISSING")).toBeInTheDocument();
  });
});
