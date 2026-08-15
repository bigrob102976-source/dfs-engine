import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AiProjectionPerformanceCard } from "../AiProjectionPerformanceCard";
import type { ProjectionSourceComparisonDocument } from "@/lib/projectionSourceComparison";

function doc(overrides: Partial<ProjectionSourceComparisonDocument> = {}): ProjectionSourceComparisonDocument {
  return {
    slate_date: "2026-08-13",
    generated_at: "2026-08-13T20:00:00+00:00",
    actual_result_count: 18,
    sources_present: ["independent", "external", "ai"],
    metrics: [
      { source: "independent", n: 18, mae: 7.54, rmse: 9.1, correlation: 0.4, rank_correlation: 0.42, top5_hit_rate: 0.6, top10_hit_rate: 0.6 },
      { source: "external", n: 18, mae: 7.01, rmse: 8.8, correlation: 0.45, rank_correlation: 0.44, top5_hit_rate: 0.6, top10_hit_rate: 0.7 },
      { source: "ai", n: 18, mae: 6.82, rmse: 8.5, correlation: 0.47, rank_correlation: 0.46, top5_hit_rate: 0.8, top10_hit_rate: 0.7 },
    ],
    ai_vs_independent_mae_improvement_percent: 9.5,
    ...overrides,
  };
}

describe("AiProjectionPerformanceCard", () => {
  it("shows a not-generated message when there is no comparison document", () => {
    render(<AiProjectionPerformanceCard doc={null} />);
    expect(screen.getByText("No evaluated slate yet.")).toBeInTheDocument();
    // Never leak a raw script path into the empty state (Milestone 16
    // removed developer CLI commands from the dashboard entirely).
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });

  it("shows a not-generated message when the document has zero metrics", () => {
    render(<AiProjectionPerformanceCard doc={doc({ metrics: [], sources_present: [] })} />);
    expect(screen.getByText("No evaluated slate yet.")).toBeInTheDocument();
  });

  it("Overall MAE headline is the AI source's MAE when AI is present", () => {
    render(<AiProjectionPerformanceCard doc={doc()} />);
    const headline = screen.getByText("Overall MAE").parentElement!;
    expect(headline.textContent).toContain("6.82");
  });

  it("renders every present source's MAE tile", () => {
    render(<AiProjectionPerformanceCard doc={doc()} />);
    expect(screen.getByText("Independent").closest("div")!.textContent).toContain("7.54");
    expect(screen.getByText("External").closest("div")!.textContent).toContain("7.01");
    expect(screen.getByText("AI").closest("div")!.textContent).toContain("6.82");
  });

  it("omits a source tile the document doesn't have data for", () => {
    render(<AiProjectionPerformanceCard doc={doc()} />);
    expect(screen.queryByText("Adjusted")).not.toBeInTheDocument();
  });

  it("shows a positive improvement figure in green with a + sign", () => {
    render(<AiProjectionPerformanceCard doc={doc()} />);
    const improvement = screen.getByText("+9.5%");
    expect(improvement).toBeInTheDocument();
    expect(improvement.className).toContain("text-green");
  });

  it("shows a negative improvement figure in red without a + sign", () => {
    render(<AiProjectionPerformanceCard doc={doc({ ai_vs_independent_mae_improvement_percent: -0.5 })} />);
    const improvement = screen.getByText("-0.5%");
    expect(improvement).toBeInTheDocument();
    expect(improvement.className).toContain("text-red");
  });

  it("hides the improvement line when null", () => {
    render(<AiProjectionPerformanceCard doc={doc({ ai_vs_independent_mae_improvement_percent: null })} />);
    expect(screen.queryByText(/Improvement/)).not.toBeInTheDocument();
  });

  it("shows the pitcher-only sample size and slate date", () => {
    render(<AiProjectionPerformanceCard doc={doc()} />);
    expect(screen.getByText(/n=18/)).toBeInTheDocument();
    expect(screen.getByText(/2026-08-13/)).toBeInTheDocument();
  });
});
