import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import TopPitchersPage from "../page";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-pitchers-page-test";
  vi.stubGlobal(
    "fetch",
    vi.fn(() => jsonResponse({ run: null })),
  );
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("TopPitchersPage (missing pitcher snapshot)", () => {
  it("shows Generate Pitcher Research instead of a developer command", async () => {
    const jsx = await TopPitchersPage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Generate Pitcher Research")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/run_real_pitcher_agent/)).not.toBeInTheDocument();
  });
});
