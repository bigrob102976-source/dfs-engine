import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("draftGroupId=151307"),
  usePathname: () => "/nfl/lineups",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn() }),
}));

vi.mock("@/lib/nfl/useNflData", () => ({
  useNflData: () => ({
    data: { slate_date: "2026-09-13", players: [] },
    loading: false, error: null, refresh: vi.fn(),
  }),
}));

import NflLineupsPage from "../page";
import { saveOptimizeResult } from "@/lib/nfl/optimizeResultStorage";
import type { NflOptimizeResult } from "@/lib/nfl/types";

function result(overrides: Partial<NflOptimizeResult> = {}): NflOptimizeResult {
  return {
    requested: 1,
    generated: 1,
    stopped_reason: null,
    mode: "projection",
    lineups: [
      {
        index: 0,
        total_salary: 49000,
        remaining_salary: 1000,
        total_projection: 120.5,
        total_ceiling: null,
        sum_ownership: null,
        average_ownership: null,
        total_leverage_score: null,
        qb_stack_team: null,
        qb_stack_receiver_count: 0,
        bring_back_player: null,
        rb_dst_team: null,
        assignments: [
          { slot: "QB", draftkings_player_id: "1", name: "Owned QB", position: "QB", team: "BUF", salary: 7000, projected_ownership: 22.4, ceiling: null },
          { slot: "DST", draftkings_player_id: "2", name: "No Own DST", position: "DST", team: "MIA", salary: 3000, projected_ownership: null, ceiling: null },
        ],
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  window.localStorage.clear();
});

describe("NFL Lineups page -- per-player Ownership (NFL M12)", () => {
  it("renders each assigned player's real ownership percentage", () => {
    saveOptimizeResult(151307, result());
    render(<NflLineupsPage />);
    expect(screen.getByText("22.4%")).toBeInTheDocument();
  });

  it("renders -- (never a fake 0%) for an assigned player with no ownership estimate", () => {
    saveOptimizeResult(151307, result());
    render(<NflLineupsPage />);
    // DST has projected_ownership: null -- its row's Ownership cell must be "--".
    const dstRow = screen.getByText("No Own DST").closest("tr");
    expect(dstRow).not.toBeNull();
    expect(dstRow?.textContent).toContain("--");
  });
});

describe("NFL Lineups page -- anonymous save prompt (NFL public access)", () => {
  const FULL_SLOTS = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"];

  function fullResult(): NflOptimizeResult {
    return result({
      lineups: [
        {
          index: 0, total_salary: 49000, remaining_salary: 1000, total_projection: 120.5,
          total_ceiling: null, sum_ownership: null, average_ownership: null, total_leverage_score: null,
          qb_stack_team: null, qb_stack_receiver_count: 0, bring_back_player: null, rb_dst_team: null,
          assignments: FULL_SLOTS.map((slot, i) => ({
            slot, draftkings_player_id: String(i), name: `Player ${i}`, position: slot.replace(/\d/, ""),
            team: "BUF", salary: 5000, projected_ownership: null, ceiling: null,
          })),
        },
      ],
    });
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a clear sign-in prompt (never a raw redirect) when saving fails with 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ error: "Authentication required." }) }));
    saveOptimizeResult(151307, fullResult());
    render(<NflLineupsPage />);

    fireEvent.click(screen.getByText("Save Lineup"));

    await waitFor(() => {
      expect(screen.getByText("Sign in to save lineups and use persistent Late Swap.")).toBeInTheDocument();
    });
  });
});

describe("NFL Lineups page -- public export (NFL public access)", () => {
  it("Export CSV calls the stateless public export route with the in-memory lineup, no login required", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ csv: "QB,RB\nA (1),B (2)\n", lineup_count: 1 }) });
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:fake");
    URL.revokeObjectURL = vi.fn();
    saveOptimizeResult(151307, result());
    render(<NflLineupsPage />);

    fireEvent.click(screen.getByText("Export CSV"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/nfl/export/public",
        expect.objectContaining({ method: "POST", body: expect.stringContaining("Owned QB") }),
      );
    });
  });
});
