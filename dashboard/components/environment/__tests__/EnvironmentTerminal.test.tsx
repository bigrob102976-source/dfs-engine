import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnvironmentTerminal } from "../EnvironmentTerminal";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";

const hitterGame = buildGameEnvironmentReport({
  game_id: "hitter-game",
  home_team: "COL",
  away_team: "PHI",
  environment_score: { overall: 90, pitcher: 10, hitter: 90, stack: 92 },
  ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 118 },
});
const pitcherGame = buildGameEnvironmentReport({
  game_id: "pitcher-game",
  home_team: "SF",
  away_team: "SD",
  environment_score: { overall: 18, pitcher: 82, hitter: 18, stack: 12 },
  ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 85 },
});

describe("EnvironmentTerminal", () => {
  it("renders a card for every game", () => {
    render(<EnvironmentTerminal games={[hitterGame, pitcherGame]} />);
    expect(screen.getByText("PHI @ COL")).toBeInTheDocument();
    expect(screen.getByText("SD @ SF")).toBeInTheDocument();
  });

  it("shows a friendly empty state when the park filter matches nothing", () => {
    render(<EnvironmentTerminal games={[hitterGame]} />);
    fireEvent.change(screen.getByDisplayValue("All Parks"), { target: { value: "pitcher" } });
    expect(screen.getByText("No games match the current filters.")).toBeInTheDocument();
  });

  it("filters down to only hitter parks", () => {
    render(<EnvironmentTerminal games={[hitterGame, pitcherGame]} />);
    fireEvent.change(screen.getByDisplayValue("All Parks"), { target: { value: "hitter" } });
    expect(screen.getByText("PHI @ COL")).toBeInTheDocument();
    expect(screen.queryByText("SD @ SF")).not.toBeInTheDocument();
  });

  it("opens the detail drawer when a card is clicked", () => {
    render(<EnvironmentTerminal games={[hitterGame, pitcherGame]} />);
    fireEvent.click(screen.getByText("PHI @ COL"));
    expect(screen.getByText("AI Summary")).toBeInTheDocument();
  });

  it("sorts by Highest Stack Rating when selected", () => {
    render(<EnvironmentTerminal games={[pitcherGame, hitterGame]} />);
    fireEvent.change(screen.getByDisplayValue("Environment Score"), { target: { value: "stack" } });
    const cards = screen.getAllByText(/@/);
    expect(cards[0]).toHaveTextContent("PHI @ COL"); // stack 92, highest first
  });
});
