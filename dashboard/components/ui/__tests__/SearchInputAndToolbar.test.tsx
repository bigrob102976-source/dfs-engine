import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SearchInput } from "../SearchInput";
import { TableToolbar } from "../TableToolbar";

describe("SearchInput", () => {
  it("renders as a search input and forwards onChange", () => {
    const onChange = vi.fn();
    render(<SearchInput placeholder="Search players..." onChange={onChange} />);
    const input = screen.getByPlaceholderText("Search players...");
    expect(input).toHaveAttribute("type", "search");
    fireEvent.change(input, { target: { value: "schwarber" } });
    expect(onChange).toHaveBeenCalled();
  });
});

describe("TableToolbar", () => {
  it("renders children and an optional result count", () => {
    render(
      <TableToolbar resultCount="12 / 40">
        <button>All teams</button>
      </TableToolbar>,
    );
    expect(screen.getByRole("button", { name: "All teams" })).toBeInTheDocument();
    expect(screen.getByText("12 / 40")).toBeInTheDocument();
  });
});
