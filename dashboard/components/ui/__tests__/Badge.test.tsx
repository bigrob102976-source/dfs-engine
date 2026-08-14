import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AIInsightBadge, EnvironmentScoreBadge, OwnershipBadge, PremiumBadge, ProjectionBadge, TagBadge } from "../Badge";

describe("Badge components", () => {
  it("ProjectionBadge renders its formatted value with a positive tone", () => {
    render(<ProjectionBadge value="+0.9" tone="positive" />);
    const badge = screen.getByText("+0.9");
    expect(badge.className).toContain("text-green");
  });

  it("ProjectionBadge renders a negative tone", () => {
    render(<ProjectionBadge value="-0.4" tone="negative" />);
    expect(screen.getByText("-0.4").className).toContain("text-red");
  });

  it("OwnershipBadge formats a percent or shows -- for null", () => {
    render(
      <>
        <OwnershipBadge percent={23.456} />
        <OwnershipBadge percent={null} />
      </>,
    );
    expect(screen.getByText("23.5%")).toBeInTheDocument();
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("AIInsightBadge is visually marked with the AI/purple accent", () => {
    render(<AIInsightBadge>positive recent hard-hit trend</AIInsightBadge>);
    const badge = screen.getByText(/positive recent hard-hit trend/);
    expect(badge.className).toContain("text-purple");
  });

  it("TagBadge renders plain research tags", () => {
    render(<TagBadge>elite_power</TagBadge>);
    expect(screen.getByText("elite_power")).toBeInTheDocument();
  });

  it("PremiumBadge uses the gold accent exclusively", () => {
    render(<PremiumBadge>PRO</PremiumBadge>);
    expect(screen.getByText("PRO").className).toContain("text-gold");
  });

  it("EnvironmentScoreBadge colors a high hitter-leaning score red (great hitting)", () => {
    render(<EnvironmentScoreBadge score={85} label="HIT" />);
    expect(screen.getByText("HIT 85").className).toContain("text-red");
  });

  it("EnvironmentScoreBadge colors a low hitter-leaning score green (great pitching)", () => {
    render(<EnvironmentScoreBadge score={15} label="HIT" />);
    expect(screen.getByText("HIT 15").className).toContain("text-green");
  });

  it("EnvironmentScoreBadge colors a truly neutral score blue", () => {
    render(<EnvironmentScoreBadge score={50} />);
    expect(screen.getByText("50").className).toContain("text-accent");
  });

  it("EnvironmentScoreBadge colors a watch-tier score amber", () => {
    render(<EnvironmentScoreBadge score={60} />);
    expect(screen.getByText("60").className).toContain("text-yellow");
  });

  it("EnvironmentScoreBadge flips its color logic for pitching-high orientation (a high Pitcher Score is pitcher-favorable)", () => {
    render(<EnvironmentScoreBadge score={85} label="PIT" orientation="pitching-high" />);
    expect(screen.getByText("PIT 85").className).toContain("text-green");
  });
});
