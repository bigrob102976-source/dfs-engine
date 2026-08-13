import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PoolTable } from "../PoolTable";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

function player(overrides: Partial<PoolPlayerRow>): PoolPlayerRow {
  return {
    dkPlayerId: "d1",
    mlbPlayerId: "h1",
    name: "Player",
    team: "AAA",
    opponent: "BBB",
    gameId: "g1",
    playerType: "hitter",
    positions: ["OF"],
    battingOrder: 1,
    salary: 4000,
    projection: 8,
    ceiling: 15,
    value: 2,
    ownership: 20,
    leverage: 5,
    risk: 30,
    confidence: 90,
    lineupStatus: "active",
    matchStatus: "matched",
    ...overrides,
  };
}

const players = [
  player({ dkPlayerId: "d1", name: "Bravo Hitter", team: "PHI", playerType: "hitter", positions: ["OF"], projection: 5 }),
  player({ dkPlayerId: "d2", name: "Alpha Hitter", team: "NYY", playerType: "hitter", positions: ["1B", "OF"], projection: 15 }),
  player({ dkPlayerId: "d3", name: "Ace Pitcher", team: "TOR", playerType: "pitcher", positions: ["P"], battingOrder: null, projection: 20 }),
];

function renderTable(overrides: Partial<Parameters<typeof PoolTable>[0]> = {}) {
  const onToggleLock = vi.fn();
  const onToggleExclude = vi.fn();
  const onExposureChange = vi.fn();
  render(
    <PoolTable
      players={players}
      locks={new Set()}
      exclusions={new Set()}
      maxExposure={{}}
      onToggleLock={onToggleLock}
      onToggleExclude={onToggleExclude}
      onExposureChange={onExposureChange}
      {...overrides}
    />,
  );
  return { onToggleLock, onToggleExclude, onExposureChange };
}

describe("PoolTable", () => {
  it("renders every player", () => {
    renderTable();
    expect(screen.getByText("Bravo Hitter")).toBeInTheDocument();
    expect(screen.getByText("Alpha Hitter")).toBeInTheDocument();
    expect(screen.getByText("Ace Pitcher")).toBeInTheDocument();
  });

  it("defaults to sorting by projection descending", () => {
    renderTable();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Ace Pitcher"); // projection 20
  });

  it("the P position tab shows only pitchers", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "P" }));
    expect(screen.getByText("Ace Pitcher")).toBeInTheDocument();
    expect(screen.queryByText("Bravo Hitter")).not.toBeInTheDocument();
  });

  it("a multi-position player appears under every eligible position tab", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "1B" }));
    expect(screen.getByText("Alpha Hitter")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "OF" }));
    expect(screen.getByText("Alpha Hitter")).toBeInTheDocument();
    expect(screen.getByText("Bravo Hitter")).toBeInTheDocument();
  });

  it("search matches name, team, and opponent", () => {
    renderTable();
    fireEvent.change(screen.getByPlaceholderText("Search players..."), { target: { value: "phi" } });
    expect(screen.getByText("Bravo Hitter")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Hitter")).not.toBeInTheDocument();
  });

  it("clicking a sortable header toggles direction", () => {
    renderTable();
    const header = screen.getByRole("columnheader", { name: /Proj/ });
    fireEvent.click(header); // ascending
    let rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Bravo Hitter"); // lowest projection (5) first
    fireEvent.click(header); // descending again
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Ace Pitcher");
  });

  it("calls onToggleLock when the Lock button is clicked", () => {
    const { onToggleLock } = renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Lock Bravo Hitter" }));
    expect(onToggleLock).toHaveBeenCalledWith("d1");
  });

  it("calls onToggleExclude when the Exclude button is clicked", () => {
    const { onToggleExclude } = renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Exclude Bravo Hitter" }));
    expect(onToggleExclude).toHaveBeenCalledWith("d1");
  });

  it("highlights a locked row and disables its exclude button", () => {
    renderTable({ locks: new Set(["d1"]) });
    expect(screen.getByRole("button", { name: "Unlock Bravo Hitter" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exclude Bravo Hitter" })).toBeDisabled();
  });

  it("highlights an excluded row and disables its lock button", () => {
    renderTable({ exclusions: new Set(["d1"]) });
    expect(screen.getByRole("button", { name: "Restore Bravo Hitter" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lock Bravo Hitter" })).toBeDisabled();
  });

  it("calls onExposureChange with a fraction when the exposure input changes", () => {
    const { onExposureChange } = renderTable();
    const row = screen.getByText("Bravo Hitter").closest("tr")!;
    const input = row.querySelector("input[type='number']") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "50" } });
    expect(onExposureChange).toHaveBeenCalledWith("d1", 0.5);
  });

  it("shows an empty state when no players match the filters", () => {
    renderTable();
    fireEvent.change(screen.getByPlaceholderText("Search players..."), { target: { value: "zzz-nobody" } });
    expect(screen.getByText("No players match the current filters.")).toBeInTheDocument();
  });

  it("blanks batting order for pitchers", () => {
    renderTable();
    const row = screen.getByText("Ace Pitcher").closest("tr")!;
    const cells = Array.from(row.querySelectorAll("td")).map((td) => td.textContent);
    // Ord column is the 7th cell (Lock, Exclude, Pos, Name, Team, Opp, Ord, ...)
    expect(cells[6]).toBe("");
  });
});
