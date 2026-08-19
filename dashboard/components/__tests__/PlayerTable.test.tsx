import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlayerTable } from "../PlayerTable";
import { numericColumn, type PlayerColumn } from "../playerColumns";
import type { PlayerRow } from "@/lib/types";

function row(overrides: Partial<PlayerRow>): PlayerRow {
  return {
    id: "1",
    playerType: "hitter",
    name: "Player",
    team: "AAA",
    opponent: "BBB",
    gameId: "g1",
    position: "OF",
    positions: ["OF"],
    battingOrder: null,
    salary: 4000,
    projection: 8.0,
    ceiling: 15.0,
    floor: 4.0,
    overall: 60.0,
    power: 50.0,
    matchup: 50.0,
    risk: 30.0,
    confidence: 90.0,
    ownership: 20.0,
    ownershipTier: "medium",
    chalkScore: 50.0,
    leverage: 5.0,
    tags: [],
    reasons: [],
    lineupStatus: null, matchStatus: null, eligibilityStatus: null, optimizerEligible: false,
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

const columns: PlayerColumn[] = [
  { key: "name", label: "Player", sortKey: "name", render: (r) => r.name },
  { key: "team", label: "Team", sortKey: "team", render: (r) => r.team },
  numericColumn("projection", "Projection"),
];

describe("PlayerTable", () => {
  const rows = [
    row({ id: "1", name: "Bravo Player", team: "PHI", projection: 5 }),
    row({ id: "2", name: "Alpha Player", team: "NYY", projection: 15 }),
  ];

  it("renders every row with its rank", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    expect(screen.getByText("Bravo Player")).toBeInTheDocument();
    expect(screen.getByText("Alpha Player")).toBeInTheDocument();
  });

  it("sorts descending by the initial sort key by default", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    const names = screen.getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(names[0]).toContain("Alpha Player"); // projection 15, highest first
  });

  it("toggles sort direction when a sortable header is clicked twice", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    // The header's accessible text includes the sort-direction arrow
    // ("Projection ▼"), so match by role + substring rather than exact text.
    const header = screen.getByRole("columnheader", { name: /Projection/ });
    fireEvent.click(header); // now ascending
    let names = screen.getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(names[0]).toContain("Bravo Player"); // lowest projection first

    fireEvent.click(header); // back to descending
    names = screen.getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(names[0]).toContain("Alpha Player");
  });

  it("filters rows by the team dropdown", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    const select = screen.getByDisplayValue("All teams");
    fireEvent.change(select, { target: { value: "PHI" } });
    expect(screen.getByText("Bravo Player")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Player")).not.toBeInTheDocument();
  });

  it("filters rows by name search", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    fireEvent.change(screen.getByPlaceholderText("Filter by name..."), { target: { value: "alpha" } });
    expect(screen.getByText("Alpha Player")).toBeInTheDocument();
    expect(screen.queryByText("Bravo Player")).not.toBeInTheDocument();
  });

  it("shows a friendly empty state when filters match nothing", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    fireEvent.change(screen.getByPlaceholderText("Filter by name..."), { target: { value: "zzz-nobody" } });
    expect(screen.getByText("No players match the current filters.")).toBeInTheDocument();
  });

  it("opens the player detail panel when a row is clicked", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" />);
    fireEvent.click(screen.getByText("Alpha Player"));
    // Detail panel renders the player's ownership stat block.
    expect(screen.getByText("Ownership")).toBeInTheDocument();
  });

  it("auto-opens the detail panel for a highlighted player id", () => {
    render(<PlayerTable rows={rows} columns={columns} initialSortKey="projection" highlightId="2" />);
    expect(screen.getByText("Ownership")).toBeInTheDocument();
  });
});
