import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, DataCard, MetricCard } from "../Card";

describe("Card family", () => {
  it("Card renders its children inside a card surface", () => {
    render(<Card>content</Card>);
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("MetricCard renders a label and value", () => {
    render(<MetricCard label="Games" value={9} />);
    expect(screen.getByText("Games")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
  });

  it("MetricCard applies positive/negative tone coloring", () => {
    render(
      <>
        <MetricCard label="Ready" value="READY" tone="positive" />
        <MetricCard label="Missing" value="MISSING" tone="negative" />
      </>,
    );
    expect(screen.getByText("READY").className).toContain("text-green");
    expect(screen.getByText("MISSING").className).toContain("text-red");
  });

  it("MetricCard renders optional trend content", () => {
    render(<MetricCard label="Pitcher MAE" value="2.10" trend={<span>▼ 0.30</span>} />);
    expect(screen.getByText("▼ 0.30")).toBeInTheDocument();
  });

  it("DataCard renders a title, optional action, and children", () => {
    render(
      <DataCard title="Top Pitchers" action={<span>View all</span>}>
        <div>list content</div>
      </DataCard>,
    );
    expect(screen.getByText("Top Pitchers")).toBeInTheDocument();
    expect(screen.getByText("View all")).toBeInTheDocument();
    expect(screen.getByText("list content")).toBeInTheDocument();
  });
});
