import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GameEnvironmentDrawer } from "../GameEnvironmentDrawer";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";

const ALL_SECTIONS = { weather: true, vegas: true, bullpen: true, park: true, travel: true };

describe("GameEnvironmentDrawer", () => {
  it("renders nothing when no game is selected", () => {
    const { container } = render(<GameEnvironmentDrawer game={null} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders every research section for a fully-populated game", () => {
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(screen.getByText("Weather")).toBeInTheDocument();
    expect(screen.getByText("Vegas")).toBeInTheDocument();
    expect(screen.getByText("Bullpen")).toBeInTheDocument();
    expect(screen.getByText("Park")).toBeInTheDocument();
    expect(screen.getByText("Umpire")).toBeInTheDocument();
    expect(screen.getByText("Travel")).toBeInTheDocument();
    expect(screen.getByText("AI Summary")).toBeInTheDocument();
    expect(screen.getByText("Future Adjustment Preview")).toBeInTheDocument();
  });

  it("shows the AI Summary bullets", () => {
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(screen.getAllByText(/Notable wind blowing out\./).length).toBeGreaterThan(0);
    expect(screen.getByText(/High implied total\./)).toBeInTheDocument();
  });

  it("shows a plain-language UNKNOWN state for a missing umpire, never a guess", () => {
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(screen.getByText(/UNKNOWN -- no umpire assignment/)).toBeInTheDocument();
  });

  it("shows an unavailable message for missing weather", () => {
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport({ weather: null })} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(screen.getByText("Weather is unavailable for this game.")).toBeInTheDocument();
  });

  it("Milestone 32.6 Part 6: shows WEATHER RISK as a percentage with a semantic GOOD/CAUTION/BAD label, never color alone", () => {
    const base = buildGameEnvironmentReport();
    render(
      <GameEnvironmentDrawer
        game={buildGameEnvironmentReport({ weather: { ...base.weather!, weather_risk_percent: 12, weather_status: "Low disruption risk" } })}
        sections={ALL_SECTIONS}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("12%")).toBeInTheDocument();
    expect(screen.getByText("GOOD")).toBeInTheDocument();
    expect(screen.getByText("Low disruption risk")).toBeInTheDocument();
  });

  it("shows a RED/BAD label for a high weather risk", () => {
    const base = buildGameEnvironmentReport();
    render(
      <GameEnvironmentDrawer
        game={buildGameEnvironmentReport({ weather: { ...base.weather!, weather_risk_percent: 82, weather_status: "High delay/postponement risk" } })}
        sections={ALL_SECTIONS}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("BAD")).toBeInTheDocument();
  });

  it("omits Postponement Risk entirely when the provider has no genuine independent signal for it, rather than showing a fabricated 0%", () => {
    const base = buildGameEnvironmentReport();
    render(
      <GameEnvironmentDrawer
        game={buildGameEnvironmentReport({ weather: { ...base.weather!, postponement_risk_percent: null } })}
        sections={ALL_SECTIONS}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Postponement Risk/)).not.toBeInTheDocument();
  });

  it("shows an unavailable message for missing vegas", () => {
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport({ vegas: null })} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(screen.getByText("Vegas lines are unavailable for this game.")).toBeInTheDocument();
  });

  it("hides a section entirely when its display toggle is off", () => {
    render(
      <GameEnvironmentDrawer
        game={buildGameEnvironmentReport()}
        sections={{ ...ALL_SECTIONS, bullpen: false }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByText("Bullpen")).not.toBeInTheDocument();
  });

  it("always renders the disabled Future Adjustment preview, never applying it", () => {
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onClose={vi.fn()} />);
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(<GameEnvironmentDrawer game={buildGameEnvironmentReport()} sections={ALL_SECTIONS} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
