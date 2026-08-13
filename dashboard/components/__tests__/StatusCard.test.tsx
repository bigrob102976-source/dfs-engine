import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusCard } from "../StatusCard";

describe("StatusCard", () => {
  it("renders READY with a formatted timestamp", () => {
    render(
      <StatusCard
        status={{
          label: "Pitcher Snapshot",
          state: "ready",
          path: "/x/pitcher_board_1.json",
          generatedAtUtc: "2026-08-11T13:24:00Z",
          generatedAtLocal: "2026-08-11T08:24:00-05:00",
        }}
      />,
    );
    expect(screen.getByText("Pitcher Snapshot")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByText(/Generated:/)).toBeInTheDocument();
  });

  it("renders MISSING with a user-facing detail and no developer command", () => {
    render(
      <StatusCard
        status={{
          label: "Ownership",
          state: "missing",
          path: null,
          generatedAtUtc: null,
          generatedAtLocal: null,
          detail: "Ownership has not been generated yet.",
        }}
      />,
    );
    expect(screen.getByText("MISSING")).toBeInTheDocument();
    expect(screen.getByText("Ownership has not been generated yet.")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });

  it("renders OUTDATED distinctly from READY/MISSING", () => {
    render(
      <StatusCard
        status={{ label: "Optimizer", state: "outdated", path: "/x.json", generatedAtUtc: "2026-08-11T10:00:00Z", generatedAtLocal: null }}
      />,
    );
    expect(screen.getByText("OUTDATED")).toBeInTheDocument();
  });
});
