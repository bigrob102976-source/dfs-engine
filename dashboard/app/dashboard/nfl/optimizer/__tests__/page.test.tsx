import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("draftGroupId=151307"),
  usePathname: () => "/dashboard/nfl/optimizer",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn() }),
}));

import NflOptimizerPage from "../page";

const SLATE_DATA = {
  draft_group_id: 151307, slate_date: "2026-09-13", slate_name: "Main", source_provenance: "x", salary_cap: 50000,
  current_season: 2026, current_week: 1, prior_season: 2025, current_completed_weeks: [], games: [], game_count: 0,
  player_count: 1, position_counts: {}, identity: { total: 1, resolved: 1, unresolved: 0 },
  projection_coverage: {}, projection_error: null, ownership_coverage: {}, ownership_generated: 0, ownership_missing: 1,
  ownership_normalization: null, ownership_model_version: null, vegas_configured: false, vegas_source_provenance: "not_configured",
  players: [
    {
      draftkings_player_id: "1", name: "Zay Flowers", position: "WR", team: "BAL", opponent: "CIN", game_id: "100",
      salary: 6400, roster_slots: ["WR", "FLEX"], is_team_entity: false, status: null, injury_status: null,
      gsis_id: null, identity_resolved: true, usage: null, projection: null, ownership: null, matchup: null,
    },
  ],
};

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (typeof url === "string" && url.includes("/api/nfl/data")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SLATE_DATA) } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ requested: 1, generated: 1, stopped_reason: null, mode: "roster_feasibility", lineups: [] }),
    } as Response);
  }));
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("NFL Optimizer page -- stacking/objective/exposure controls (NFL M13)", () => {
  it("renders the Stacking section with QB Stack, Bring Back, RB+DST, and team/game limit controls", async () => {
    render(<NflOptimizerPage />);
    await waitFor(() => expect(screen.getByText("Stacking")).toBeInTheDocument());
    expect(screen.getByText("QB Stack")).toBeInTheDocument();
    expect(screen.getByText("Bring Back")).toBeInTheDocument();
    expect(screen.getByText("RB + DST")).toBeInTheDocument();
    expect(screen.getByText("Max Players / Team")).toBeInTheDocument();
    expect(screen.getByText("Max Players / Game")).toBeInTheDocument();
  });

  it("Bring Back select is disabled until QB Stack is enabled", async () => {
    render(<NflOptimizerPage />);
    await waitFor(() => expect(screen.getByLabelText("Bring Back")).toBeInTheDocument());
    const bringBackSelect = screen.getByLabelText("Bring Back") as HTMLSelectElement;
    expect(bringBackSelect.disabled).toBe(true);

    const qbStackSelect = screen.getByLabelText("QB Stack") as HTMLSelectElement;
    fireEvent.change(qbStackSelect, { target: { value: "single" } });
    expect(bringBackSelect.disabled).toBe(false);
  });

  it("renders all four Objective options including Ceiling and Leverage", async () => {
    render(<NflOptimizerPage />);
    await waitFor(() => expect(screen.getByLabelText("Objective")).toBeInTheDocument());
    const select = screen.getByLabelText("Objective") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toEqual(["roster_feasibility", "projection", "ceiling", "leverage"]);
  });

  it("shows the Exposure section with a Default Max Exposure input", async () => {
    render(<NflOptimizerPage />);
    await waitFor(() => expect(screen.getByText("Exposure")).toBeInTheDocument());
    expect(screen.getByLabelText(/Default Max Exposure/)).toBeInTheDocument();
  });

  it("Build Lineups POSTs the selected stack config to /api/nfl/optimize", async () => {
    render(<NflOptimizerPage />);
    await waitFor(() => expect(screen.getByText("Stacking")).toBeInTheDocument());

    const qbStackSelect = screen.getByLabelText("QB Stack") as HTMLSelectElement;
    fireEvent.change(qbStackSelect, { target: { value: "double" } });

    fireEvent.click(screen.getByText("Build Lineups"));

    await waitFor(() => {
      const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
      const optimizeCall = calls.find((c) => typeof c[0] === "string" && c[0].includes("/api/nfl/optimize"));
      expect(optimizeCall).toBeDefined();
      const body = JSON.parse(optimizeCall![1].body as string);
      expect(body.stack.qbStackMode).toBe("double");
    });
  });
});
