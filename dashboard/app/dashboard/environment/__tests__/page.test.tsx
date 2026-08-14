import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import EnvironmentPage from "../page";

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-environment-page-test";
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  vi.restoreAllMocks();
});

describe("EnvironmentPage (no snapshot yet)", () => {
  it("shows a friendly empty state with a Generate action, never a raw script command", () => {
    render(<EnvironmentPage />);
    expect(screen.getByText("No Game Environment report yet for today's slate")).toBeInTheDocument();
    expect(screen.getByText("Generate Environment Report")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });
});
