import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import StacksPage from "../page";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-stacks-page-test";
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

describe("StacksPage (missing batter snapshot)", () => {
  it("shows Refresh Required Data instead of a developer command", () => {
    render(<StacksPage />);

    expect(screen.getByText("Refresh Required Data")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
  });
});
