import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CommandCenterHeader } from "../CommandCenterHeader";

function baseProps(overrides: Partial<Parameters<typeof CommandCenterHeader>[0]> = {}) {
  return {
    date: "2026-08-24",
    gameCount: 7,
    providerName: "draftkings_unofficial",
    isMock: false,
    selectedSlateId: null,
    lastUpdated: null,
    viewingSlateLabel: null,
    ...overrides,
  };
}

// Optimizer correctness hotfix: reproduced live -- this header's "Slate"
// link always pointed at bare /dashboard/optimizer with no slate param,
// even when a real slate was selected (shown right there in the link's
// own label), so clicking through silently lost the currently-selected
// global slate and landed the Optimizer on its own independent
// (localStorage-persisted) selection instead.
describe("CommandCenterHeader", () => {
  it("carries the currently-selected slate onto the Optimizer link as ?slate=", () => {
    render(<CommandCenterHeader {...baseProps({ selectedSlateId: "dkunofficial-152567" })} />);
    const link = screen.getByRole("link", { name: /Slate/i });
    expect(link).toHaveAttribute("href", "/dashboard/optimizer?slate=dkunofficial-152567");
    expect(link).toHaveTextContent("dkunofficial-152567");
  });

  it("links to bare /dashboard/optimizer (no slate param) when nothing is selected -- prompts selection there instead", () => {
    render(<CommandCenterHeader {...baseProps({ selectedSlateId: null })} />);
    const link = screen.getByRole("link", { name: /Slate/i });
    expect(link).toHaveAttribute("href", "/dashboard/optimizer");
    expect(link).toHaveTextContent("Select in Optimizer");
  });

  it("URL-encodes a slate id containing special characters", () => {
    render(<CommandCenterHeader {...baseProps({ selectedSlateId: "dk&unofficial 152567" })} />);
    expect(screen.getByRole("link", { name: /Slate/i })).toHaveAttribute("href", "/dashboard/optimizer?slate=dk%26unofficial%20152567");
  });

  it("still shows the game count, date, and viewing label", () => {
    render(<CommandCenterHeader {...baseProps({ viewingSlateLabel: "Featured", gameCount: 7 })} />);
    expect(screen.getByText(/7 games/)).toBeInTheDocument();
    expect(screen.getByText("Featured")).toBeInTheDocument();
  });
});
