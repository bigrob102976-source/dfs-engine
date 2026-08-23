import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PythonRunner, PythonRunResult } from "@/lib/orchestrator/pythonRunner";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/memberSlateVisibility", () => ({
  filterSlatesForCurrentViewer: async (slates: unknown) => slates,
}));

function ok(stdout: string): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}

const NO_SLATES = ok(
  JSON.stringify({
    status: "not_connected", reason: null, provider_name: null, provider_type: null,
    is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
  }),
);

function makeSlateRunner(slatesResult: PythonRunResult = NO_SLATES): PythonRunner {
  return async (script) => {
    if (script === "scripts/list_dfs_slates.py") return slatesResult;
    throw new Error(`Unexpected script call in test: ${script}`);
  };
}

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-health-page-test";
});

afterEach(async () => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  vi.restoreAllMocks();
});

describe("ModelHealthPage -- Milestone 32.6 Part 1/10: respects the global slate context", () => {
  it("never crashes with no snapshot and no slate selected", async () => {
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeSlateRunner());

    const ModelHealthPage = (await import("../page")).default;
    const jsx = await ModelHealthPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Model Health")).toBeInTheDocument();
  });

  it("shows the selected slate's label in the page description", async () => {
    const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeSlateRunner(
        ok(
          JSON.stringify({
            status: "ready", reason: null, provider_name: "DRAFTKINGS_UNOFFICIAL_LIVE", provider_type: "real",
            is_mock: false, is_connected: true, source: "live",
            slates: [{ slate_id: "night", slate_name: "Night", game_count: 3, start_time: null, game_ids: ["g1"], player_count: 50 }],
            slates_available: 1,
          }),
        ),
      ),
    );

    const ModelHealthPage = (await import("../page")).default;
    const jsx = await ModelHealthPage({ searchParams: Promise.resolve({ slate: "night" }) } as never);
    render(jsx);

    expect(screen.getByText(/Night/)).toBeInTheDocument();
  });
});
