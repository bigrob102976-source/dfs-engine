import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlayerDetailPanel } from "../PlayerDetailPanel";
import type { OwnershipPlayer, PlayerRow } from "@/lib/types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1",
    playerType: "hitter",
    name: "Kyle Schwarber",
    team: "PHI",
    opponent: "ATL",
    gameId: "g1",
    position: "OF",
    positions: ["OF"],
    battingOrder: 3,
    salary: 5200,
    projection: 11.9,
    ceiling: 21.0,
    floor: 5.5,
    overall: 82,
    power: 90,
    matchup: 60,
    risk: 35,
    confidence: 85,
    ownership: 24.5,
    ownershipTier: "high",
    chalkScore: 70,
    leverage: -3.2,
    tags: ["elite_power", "platoon_advantage"],
    reasons: ["0.400 season xwOBA reflects elite underlying hitting skill.", "30.0% barrel rate gives him one of the strongest power profiles."],
    lineupStatus: null,
    matchStatus: null,
    raw: {
      snapshot: {
        season_metrics: { xwoba: 0.4, barrel_percent: 30.0 },
        recent_metrics: { xwoba: 0.38, hard_hit_percent: 55.6 },
        trend_metrics: { xwoba_trend: 0.02, hard_hit_trend: 4.4 },
      },
      ownership: { feature_breakdown: { chalk_score: 70, popularity_score: 65 } } as unknown as OwnershipPlayer,
      pool: null,
    },
    ...overrides,
  };
}

describe("PlayerDetailPanel", () => {
  it("renders nothing when no row is selected", () => {
    const { container } = render(<PlayerDetailPanel row={null} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the player name, team, and Overview section", () => {
    render(<PlayerDetailPanel row={row()} onClose={vi.fn()} />);
    expect(screen.getByText("Kyle Schwarber")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Projection")).toBeInTheDocument();
    expect(screen.getByText("11.9")).toBeInTheDocument();
    expect(screen.getByText("Ownership")).toBeInTheDocument();
    expect(screen.getByText("24.5%")).toBeInTheDocument();
  });

  it("renders tags as badges", () => {
    render(<PlayerDetailPanel row={row()} onClose={vi.fn()} />);
    expect(screen.getByText("elite_power")).toBeInTheDocument();
    expect(screen.getByText("platoon_advantage")).toBeInTheDocument();
  });

  it("renders AI Notes from the reasons list", () => {
    render(<PlayerDetailPanel row={row()} onClose={vi.fn()} />);
    expect(screen.getByText("AI Notes")).toBeInTheDocument();
    expect(screen.getByText(/0\.400 season xwOBA reflects elite underlying hitting skill\./)).toBeInTheDocument();
  });

  it("does not render an AI Notes section when there are no reasons", () => {
    render(<PlayerDetailPanel row={row({ reasons: [] })} onClose={vi.fn()} />);
    expect(screen.queryByText("AI Notes")).not.toBeInTheDocument();
  });

  it("renders a Research section from season/trend metrics", () => {
    render(<PlayerDetailPanel row={row()} onClose={vi.fn()} />);
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(screen.getByText("Season Metrics")).toBeInTheDocument();
    expect(screen.getByText("Trend Metrics")).toBeInTheDocument();
  });

  it("renders a Recent Form section from recent_metrics", () => {
    render(<PlayerDetailPanel row={row()} onClose={vi.fn()} />);
    expect(screen.getByText("Recent Form")).toBeInTheDocument();
  });

  it("renders an Ownership Feature Breakdown when ownership data exists", () => {
    render(<PlayerDetailPanel row={row()} onClose={vi.fn()} />);
    expect(screen.getByText("Ownership Feature Breakdown")).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(<PlayerDetailPanel row={row()} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(<PlayerDetailPanel row={row()} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("gracefully omits Research/Recent Form/Ownership sections when the underlying data is absent", () => {
    render(
      <PlayerDetailPanel
        row={row({ raw: { snapshot: {}, ownership: null, pool: null } })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByText("Research")).not.toBeInTheDocument();
    expect(screen.queryByText("Ownership Feature Breakdown")).not.toBeInTheDocument();
  });
});
