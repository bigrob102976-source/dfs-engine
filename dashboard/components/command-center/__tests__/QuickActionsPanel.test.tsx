import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QuickActionsPanel } from "../QuickActionsPanel";

const EXPECTED_LINKS: Array<[string, string]> = [
  ["Build Lineups", "/dashboard/optimizer"],
  ["Top Hitters", "/dashboard/hitters"],
  ["Top Pitchers", "/dashboard/pitchers"],
  ["Stacks", "/dashboard/stacks"],
  ["Ownership", "/dashboard/ownership"],
  ["Weather", "/dashboard/environment"],
  ["Vegas", "/dashboard/vegas"],
  ["Yesterday", "/dashboard/yesterday"],
  ["History", "/dashboard/history"],
  ["Portfolio", "/dashboard/portfolio"],
];

describe("QuickActionsPanel", () => {
  it("links every quick action to its existing page -- never a new/duplicated view", () => {
    render(<QuickActionsPanel />);
    for (const [label, href] of EXPECTED_LINKS) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it("Weather points at the real Game Environment data, not the dead-end placeholder page", () => {
    render(<QuickActionsPanel />);
    expect(screen.getByRole("link", { name: "Weather" })).toHaveAttribute("href", "/dashboard/environment");
  });

  it("Milestone 29: never renders Import Projections or a Refresh Research control -- both are admin-only operations now", () => {
    render(<QuickActionsPanel />);
    expect(screen.queryByRole("link", { name: "Import Projections" })).not.toBeInTheDocument();
    expect(screen.queryByText("Refresh Research")).not.toBeInTheDocument();
  });

  // Optimizer correctness hotfix: reproduced live -- clicking "Build
  // Lineups" (or any other slate-scoped quick action) from Command
  // Center used to always land on /dashboard/optimizer with no slate
  // context at all, so the Optimizer fell back to its own independent
  // (localStorage-persisted) slate selection instead of whatever slate
  // a member was actually looking at on Command Center.
  it("carries the currently-selected global slate onto every slate-scoped quick action", () => {
    render(<QuickActionsPanel selectedSlateId="dkunofficial-152567" />);
    expect(screen.getByRole("link", { name: "Build Lineups" })).toHaveAttribute("href", "/dashboard/optimizer?slate=dkunofficial-152567");
    expect(screen.getByRole("link", { name: "Top Hitters" })).toHaveAttribute("href", "/dashboard/hitters?slate=dkunofficial-152567");
    expect(screen.getByRole("link", { name: "Top Pitchers" })).toHaveAttribute("href", "/dashboard/pitchers?slate=dkunofficial-152567");
    expect(screen.getByRole("link", { name: "Stacks" })).toHaveAttribute("href", "/dashboard/stacks?slate=dkunofficial-152567");
    expect(screen.getByRole("link", { name: "Ownership" })).toHaveAttribute("href", "/dashboard/ownership?slate=dkunofficial-152567");
    expect(screen.getByRole("link", { name: "Vegas" })).toHaveAttribute("href", "/dashboard/vegas?slate=dkunofficial-152567");
  });

  it("never carries a slate param onto destinations with no per-slate concept", () => {
    render(<QuickActionsPanel selectedSlateId="dkunofficial-152567" />);
    expect(screen.getByRole("link", { name: "Weather" })).toHaveAttribute("href", "/dashboard/environment");
    expect(screen.getByRole("link", { name: "Yesterday" })).toHaveAttribute("href", "/dashboard/yesterday");
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "/dashboard/history");
    expect(screen.getByRole("link", { name: "Portfolio" })).toHaveAttribute("href", "/dashboard/portfolio");
  });

  it("URL-encodes a slate id containing special characters", () => {
    render(<QuickActionsPanel selectedSlateId="dk&unofficial 152567" />);
    expect(screen.getByRole("link", { name: "Build Lineups" })).toHaveAttribute("href", "/dashboard/optimizer?slate=dk%26unofficial%20152567");
  });

  it("no selectedSlateId (null, same as the no-props default) never appends a slate param -- unchanged pre-hotfix behavior", () => {
    render(<QuickActionsPanel selectedSlateId={null} />);
    for (const [label, href] of EXPECTED_LINKS) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });
});
