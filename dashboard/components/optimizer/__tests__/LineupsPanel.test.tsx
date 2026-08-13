import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LineupsPanel } from "../LineupsPanel";
import type { OptimizerBuildResult } from "@/lib/optimizerWorkspace/types";
import type { Lineup, LineupAssignment } from "@/lib/types";

function assignment(overrides: Partial<LineupAssignment> = {}): LineupAssignment {
  return {
    slot: "OF",
    dk_player_id: "d1",
    mlb_player_id: "h1",
    name: "Player A",
    team: "PHI",
    opponent: "NYM",
    salary: 4000,
    projection: 10,
    ceiling: 18,
    floor: 5,
    risk_score: 30,
    confidence: 80,
    projected_ownership: 20,
    ...overrides,
  };
}

function lineup(overrides: Partial<Lineup> = {}): Lineup {
  return {
    index: 1,
    assignments: [assignment()],
    salary: 40000,
    remaining_salary: 10000,
    projection: 100,
    ceiling: 180,
    floor: 50,
    average_risk: 30,
    average_confidence: 80,
    team_counts: {},
    primary_stack_team: "PHI",
    primary_stack_size: 5,
    sum_ownership: 150,
    average_ownership: 15,
    max_ownership: 30,
    players_above_chalk_threshold: 2,
    ...overrides,
  };
}

function result(overrides: Partial<OptimizerBuildResult> = {}): OptimizerBuildResult {
  return {
    ok: true,
    errors: [],
    lineupSetPath: "C:\\fake\\lineups\\2026-08-12\\dk_lineups_20260812T000000.json",
    csvPath: "C:\\fake\\lineups\\2026-08-12\\dk_lineups_20260812T000000.csv",
    lineupsRequested: 1,
    lineupsGenerated: 1,
    stoppedReason: null,
    lineups: [lineup()],
    elapsedMs: 1234,
    ...overrides,
  };
}

describe("LineupsPanel", () => {
  it("shows a friendly message when zero lineups were generated", () => {
    render(<LineupsPanel result={result({ lineups: [] })} />);
    expect(screen.getByText("No lineups were generated.")).toBeInTheDocument();
  });

  it("shows generated/requested counts and elapsed time", () => {
    render(<LineupsPanel result={result()} />);
    expect(screen.getByText(/Generated/)).toBeInTheDocument();
    expect(screen.getByText("1.2s", { exact: false })).toBeInTheDocument();
  });

  it("shows the stopped reason when present", () => {
    render(<LineupsPanel result={result({ stoppedReason: "Requested 20 but only 5 unique legal lineups could be generated." })} />);
    expect(screen.getByText(/only 5 unique legal lineups/)).toBeInTheDocument();
  });

  it("expands a lineup's roster on click", () => {
    const { container } = render(<LineupsPanel result={result()} />);
    // "Player A" already appears once in the Player Exposure summary --
    // expanding the roster adds a second occurrence (the roster row).
    expect(screen.getAllByText("Player A")).toHaveLength(1);
    const lineupRow = container.querySelector("table tbody tr")!;
    fireEvent.click(lineupRow);
    expect(screen.getAllByText("Player A")).toHaveLength(2);
  });

  it("renders an export link pointing at the API with the csv path", () => {
    render(<LineupsPanel result={result()} />);
    const link = screen.getByRole("link", { name: /export lineups/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("/api/optimizer/export?path="));
    expect(link).toHaveAttribute("download");
  });

  it("renders player, pitcher, and team stack exposure tables", () => {
    const lineups = [
      lineup({ index: 1, assignments: [assignment({ dk_player_id: "d1", name: "Hitter A", slot: "OF" }), assignment({ dk_player_id: "d2", name: "Pitcher A", slot: "P" })], primary_stack_team: "PHI" }),
      lineup({ index: 2, assignments: [assignment({ dk_player_id: "d1", name: "Hitter A", slot: "OF" })], primary_stack_team: "NYY" }),
    ];
    render(<LineupsPanel result={result({ lineups, lineupsGenerated: 2 })} />);
    expect(screen.getByText("Player Exposure")).toBeInTheDocument();
    expect(screen.getByText("Pitcher Exposure")).toBeInTheDocument();
    expect(screen.getByText("Team Stack Exposure")).toBeInTheDocument();
    expect(screen.getAllByText("Hitter A").length).toBeGreaterThan(0);
  });

  it("paginates when there are more than 25 lineups", () => {
    const many = Array.from({ length: 30 }, (_, i) => lineup({ index: i + 1 }));
    render(<LineupsPanel result={result({ lineups: many, lineupsGenerated: 30, lineupsRequested: 30 })} />);
    expect(screen.getByText("Page 1 / 2")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Page 2 / 2")).toBeInTheDocument();
  });
});
