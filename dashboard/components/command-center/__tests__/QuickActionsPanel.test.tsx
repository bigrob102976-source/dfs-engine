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
});
