import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import YesterdayPage from "../page";

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-yesterday-page-test";
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
});

describe("YesterdayPage (no evaluated slate -- historical/read-only)", () => {
  it("shows a plain unavailable message with no developer command and no generate button", () => {
    render(<YesterdayPage />);

    expect(screen.getByText("Historical data unavailable for this slate.")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
    // Historical pages must not offer a rebuild action unless explicitly supported.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
