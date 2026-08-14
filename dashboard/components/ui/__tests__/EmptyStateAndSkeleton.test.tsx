import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "../EmptyState";
import { LoadingOverlay, Skeleton, SkeletonCard, SkeletonTable } from "../Skeleton";

describe("EmptyState", () => {
  it("renders an icon, title, and description", () => {
    render(<EmptyState icon="📭" title="Nothing here" description="Come back after the next refresh." />);
    expect(screen.getByText("📭")).toBeInTheDocument();
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Come back after the next refresh.")).toBeInTheDocument();
  });

  it("renders an optional action", () => {
    render(<EmptyState title="Nothing here" action={<button>Refresh</button>} />);
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });

  it("never renders a raw terminal command or script path", () => {
    render(<EmptyState title="Batter research is not ready" description="Generate today's hitter research to view projections." />);
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });
});

describe("Loading states", () => {
  it("Skeleton renders a hidden placeholder block", () => {
    const { container } = render(<Skeleton className="h-4 w-10" />);
    const el = container.firstChild as HTMLElement;
    expect(el).toHaveAttribute("aria-hidden", "true");
    expect(el.className).toContain("animate-pulse");
  });

  it("SkeletonCard renders without crashing", () => {
    const { container } = render(<SkeletonCard />);
    expect(container.firstChild).toBeTruthy();
  });

  it("SkeletonTable renders the requested number of shimmering rows", () => {
    const { container } = render(<SkeletonTable rows={4} />);
    const rowSkeletons = container.querySelectorAll(".divide-y > div");
    expect(rowSkeletons).toHaveLength(4);
  });

  it("LoadingOverlay announces itself to assistive tech via role=status", () => {
    render(<LoadingOverlay label="Building lineups..." />);
    expect(screen.getByRole("status")).toHaveTextContent("Building lineups...");
  });
});
