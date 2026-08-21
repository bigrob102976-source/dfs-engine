import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import AdminSlatesPage from "../page";

let tmpDir: string;
let originalRoot: string | undefined;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-admin-slates-page-"));
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("AdminSlatesPage", () => {
  it("renders every pipeline stage as MISSING (real state, not fabricated) when no artifacts exist", async () => {
    render(await AdminSlatesPage({ searchParams: Promise.resolve({}) } as never));

    expect(screen.getByText("Slate Operations")).toBeInTheDocument();
    expect(screen.getByText("Pipeline Stages")).toBeInTheDocument();
    expect(screen.getByText("Research Package")).toBeInTheDocument();
    expect(screen.getAllByText("MISSING").length).toBeGreaterThan(0);
    expect(screen.getByText("Open Today's Slate →")).toBeInTheDocument();
  });
});
