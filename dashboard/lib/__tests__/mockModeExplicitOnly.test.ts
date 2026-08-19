import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Milestone 13 originally forbade any mention of a manual CSV upload in the
// normal refresh flow, since DFS salary data was meant to arrive only via
// the (at the time, mock-only) provider layer. Milestone 19 deliberately
// supersedes that: DraftKings has no documented public API, so uploading
// the REAL, official DraftKings salary-export CSV a user downloads
// themselves is now the highest-priority, most-real data source (see
// dfs/providers/base.py's no-scrape rule and
// dfs/providers/draftkings_csv_provider.py).
//
// Milestone 29: the member-facing RefreshPanel (which used to host an
// "Enable Mock Mode" button) was removed entirely -- Mock Mode is an
// admin-only settings toggle now (components/MockModeToggle.tsx, on the
// admin-only /dashboard/settings page; its own API route,
// /api/settings/mock-mode, requires requireAdminApi()). This file's guard
// moves with it.
//
// What must still hold, and what this file guards: mock data is NEVER
// enabled automatically. Turning it on is always one explicit user
// action (a toggle click), never something that fires on page load or as
// a fallback inside a data-fetching effect.
describe("mock mode is never enabled automatically", () => {
  it("MockModeToggle defines handleToggle as a standalone function wired only to the switch's onClick", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../components/MockModeToggle.tsx"), "utf-8");
    expect(source).toMatch(/function handleToggle\(\)/);
    expect(source).toMatch(/onClick=\{handleToggle\}/);
    // Never called eagerly at the top of an effect body.
    expect(source).not.toMatch(/useEffect\(\(\)\s*=>\s*\{\s*(\/\/[^\n]*\n\s*)*handleToggle/);
  });

  it("MockModeToggle never fetches the mock-mode endpoint outside handleToggle", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../components/MockModeToggle.tsx"), "utf-8");
    const occurrences = source.split('"/api/settings/mock-mode"').length - 1;
    expect(occurrences).toBe(1);
  });

  it("the DEV MODE banner (app/dashboard/layout.tsx) only reads Mock Mode state, never sets it", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../app/dashboard/layout.tsx"), "utf-8");
    expect(source).toContain("getMockModeEnabled");
    expect(source).not.toContain("setMockModeEnabled");
    expect(source).not.toContain('"/api/settings/mock-mode"');
  });

  it("Milestone 29: /api/settings/mock-mode requires admin -- never member-controllable", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../app/api/settings/mock-mode/route.ts"), "utf-8");
    expect(source).toContain("requireAdminApi");
  });
});
