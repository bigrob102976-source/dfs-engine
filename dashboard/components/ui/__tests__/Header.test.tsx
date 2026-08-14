import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageHeader, SectionHeader } from "../Header";

describe("PageHeader", () => {
  it("renders a title", () => {
    render(<PageHeader title="Optimizer" />);
    expect(screen.getByRole("heading", { name: "Optimizer", level: 1 })).toBeInTheDocument();
  });

  it("renders an optional description and actions", () => {
    render(<PageHeader title="Optimizer" description="Build lineups." actions={<button>Export</button>} />);
    expect(screen.getByText("Build lineups.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
  });
});

describe("SectionHeader", () => {
  it("renders a title and optional action", () => {
    render(<SectionHeader title="Artifact Detail" action={<button>Refresh</button>} />);
    expect(screen.getByText("Artifact Detail")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });
});
