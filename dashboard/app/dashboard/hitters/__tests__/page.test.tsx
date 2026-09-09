import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
  usePathname: () => "/dashboard/hitters",
  useSearchParams: () => new URLSearchParams(),
}));

// Milestone 29: resolveSlateContext() filters slates to PUBLISHED-only
// for a non-admin viewer -- this file's fixtures predate that filter,
// so pass every slate through unchanged (as an ADMIN viewer would see it).
vi.mock("@/lib/memberSlateVisibility", () => ({
  filterSlatesForCurrentViewer: async (slates: unknown) => slates,
}));

// resolveSlateContext (used by every /dashboard/* page) now picks its
// serving backend the same way /api/optimizer/slates does
// (lib/servingBackend/config.ts) instead of calling poolCache.listSlates
// directly -- getCurrentUser() calls next/headers cookies(), which
// throws outside a real request scope, so it's stubbed to null here
// (this file's own focus is the page's rendering, not backend
// selection -- covered by servingBackend/__tests__/config.test.ts).
// resolveServingBackend is stubbed to the REAL LegacyR2ServingBackend so
// listSlates keeps running for real exactly as it did before this
// change, unchanged for every test below.
vi.mock("@/lib/auth/session", () => ({ getCurrentUser: vi.fn(async () => null) }));
vi.mock("@/lib/servingBackend/config", () => ({
  resolveServingBackend: vi.fn(async () => {
    const { LegacyR2ServingBackend } = await import("@/lib/servingBackend/legacyR2Backend");
    return LegacyR2ServingBackend;
  }),
}));

import TopHittersPage from "../page";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let originalRoot: string | undefined;

beforeEach(async () => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-hitters-page-test";
  vi.stubGlobal(
    "fetch",
    vi.fn(() => jsonResponse({ run: null })),
  );
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async () => ({
    exitCode: 0,
    stdout: JSON.stringify({
      status: "not_connected", reason: null, provider_name: null, provider_type: null,
      is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
    }),
    stderr: "",
    command: [],
  }));
});

afterEach(async () => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

describe("TopHittersPage (missing batter snapshot)", () => {
  it("shows Generate Batter Research instead of a developer command", async () => {
    const jsx = await TopHittersPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Generate Batter Research")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/run_real_batter_agent/)).not.toBeInTheDocument();
  });
});
