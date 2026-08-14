import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GameEnvironmentCard } from "../GameEnvironmentCard";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";

const ALL_SECTIONS = { weather: true, vegas: true, bullpen: true, park: true };

describe("GameEnvironmentCard", () => {
  it("renders teams, environment score, and quick facts", () => {
    render(<GameEnvironmentCard game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onOpen={vi.fn()} />);
    expect(screen.getByText("CLE @ DET")).toBeInTheDocument();
    expect(screen.getByText("ENV 61")).toBeInTheDocument();
    expect(screen.getByText("Comerica Park", { exact: false })).toBeInTheDocument();
  });

  it("shows UNKNOWN for a missing umpire regardless of section toggles", () => {
    render(<GameEnvironmentCard game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onOpen={vi.fn()} />);
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
  });

  it("shows Unavailable for missing weather", () => {
    render(<GameEnvironmentCard game={buildGameEnvironmentReport({ weather: null })} sections={ALL_SECTIONS} onOpen={vi.fn()} />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("hides a section entirely when its toggle is off", () => {
    render(
      <GameEnvironmentCard
        game={buildGameEnvironmentReport()}
        sections={{ ...ALL_SECTIONS, weather: false }}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.queryByText("Weather", { exact: false })).not.toBeInTheDocument();
  });

  it("calls onOpen when clicked", () => {
    const onOpen = vi.fn();
    render(<GameEnvironmentCard game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onOpen={onOpen} />);
    fireEvent.click(screen.getByText("CLE @ DET"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
