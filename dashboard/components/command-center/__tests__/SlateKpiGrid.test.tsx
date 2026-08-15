import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SlateKpiGrid } from "../SlateKpiGrid";
import type { SlateKpi } from "@/lib/commandCenter";

function kpi(overrides: Partial<SlateKpi> = {}): SlateKpi {
  return { key: "games", label: "Games", value: 14, numeric: 14, ...overrides };
}

describe("SlateKpiGrid", () => {
  it("renders every KPI's label and sub-label", () => {
    render(<SlateKpiGrid kpis={[kpi({ key: "games", label: "Games", value: 14, numeric: 14 }), kpi({ key: "topStack", label: "Top Stack", value: "DET", numeric: undefined, sub: "10.2 proj/player" })]} />);
    expect(screen.getByText("Games")).toBeInTheDocument();
    expect(screen.getByText("Top Stack")).toBeInTheDocument();
    expect(screen.getByText("DET")).toBeInTheDocument();
    expect(screen.getByText("10.2 proj/player")).toBeInTheDocument();
  });

  it("renders the exact responsive grid shape the dashboard's responsive test depends on", () => {
    const { container } = render(<SlateKpiGrid kpis={[kpi()]} />);
    const grid = container.querySelector(".grid.grid-cols-2");
    expect(grid).toBeTruthy();
    expect(grid?.className).toContain("md:grid-cols-3");
    expect(grid?.className).toContain("lg:grid-cols-6");
  });

  it("renders a non-numeric card's value directly without animation", () => {
    render(<SlateKpiGrid kpis={[kpi({ key: "topPitcher", label: "Top Pitcher", value: "Tarik Skubal", numeric: undefined })]} />);
    expect(screen.getByText("Tarik Skubal")).toBeInTheDocument();
  });

  it("never throws for an empty KPI list", () => {
    render(<SlateKpiGrid kpis={[]} />);
  });
});
