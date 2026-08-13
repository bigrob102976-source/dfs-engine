import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Milestone 13: the normal dashboard workflow must never require a manual
// DraftKings CSV upload -- DFS salary data is fetched automatically via
// the provider layer (dfs/providers/). A file-upload CSV path may still
// exist as a debug/fallback CLI tool (scripts/build_dk_player_pool.py),
// but nothing on the primary "Today's Slate" page should ask the user to
// pick or upload a file.
describe("no manual upload required in normal flow", () => {
  it("the Today's Slate page contains no file-upload input", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../app/dashboard/page.tsx"), "utf-8");
    expect(source).not.toMatch(/type=["']file["']/i);
    expect(source.toLowerCase()).not.toContain("csv");
  });

  it("the RefreshPanel component contains no file-upload input", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../components/RefreshPanel.tsx"), "utf-8");
    expect(source).not.toMatch(/type=["']file["']/i);
    expect(source.toLowerCase()).not.toContain("csv");
  });
});
