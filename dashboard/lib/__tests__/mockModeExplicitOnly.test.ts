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
// dfs/providers/draftkings_csv_provider.py) -- RefreshPanel is expected to
// mention CSV and render a file input now.
//
// What must still hold, and what this file guards instead: mock data is
// NEVER enabled automatically. Turning it on is always one explicit user
// action (a button click), never something that fires on page load or as
// a fallback inside a data-fetching effect.
describe("mock mode is never enabled automatically", () => {
  it("RefreshPanel defines handleEnableMockMode as a standalone function wired only to a button's onClick", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../components/RefreshPanel.tsx"), "utf-8");
    expect(source).toMatch(/async function handleEnableMockMode\(\)/);
    expect(source).toMatch(/onClick=\{handleEnableMockMode\}/);
    // Never called eagerly at the top of an effect body.
    expect(source).not.toMatch(/useEffect\(\(\)\s*=>\s*\{\s*(\/\/[^\n]*\n\s*)*handleEnableMockMode/);
  });

  it("RefreshPanel never fetches the mock-mode endpoint outside handleEnableMockMode", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../components/RefreshPanel.tsx"), "utf-8");
    const occurrences = source.split('"/api/settings/mock-mode"').length - 1;
    expect(occurrences).toBe(1);
  });

  it("the DEV MODE banner (app/dashboard/layout.tsx) only reads Mock Mode state, never sets it", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "../../app/dashboard/layout.tsx"), "utf-8");
    expect(source).toContain("getMockModeEnabled");
    expect(source).not.toContain("setMockModeEnabled");
    expect(source).not.toContain('"/api/settings/mock-mode"');
  });
});
