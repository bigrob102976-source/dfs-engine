import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("draftGroupId=151307"),
  usePathname: () => "/dashboard/nfl/lineups",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn() }),
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
