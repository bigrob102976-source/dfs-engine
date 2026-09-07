import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUsePathname = vi.fn();
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useSearchParams: () => mockSearchParams,
}));

import { Sidebar } from "../Sidebar";

beforeEach(() => {
  window.localStorage.clear();
  mockUsePathname.mockReturnValue("/dashboard");
  mockSearchParams = new URLSearchParams();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Sidebar", () => {
  it("renders every required navigation item", () => {
    render(<Sidebar />);
    for (const label of [
      "Dashboard", "Research", "Pitchers", "Hitters", "Stacks", "Weather", "Vegas",
      "Ownership", "Optimizer", "Portfolio", "Results", "Model Health",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("does not render Settings -- Milestone 29 moved DFS data-provider settings to admin-only", () => {
    render(<Sidebar />);
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
  });

  it("renders the BIG MONEY DFS wordmark and subtitle when expanded", () => {
    render(<Sidebar />);
    expect(screen.getByText("BIG MONEY")).toBeInTheDocument();
    expect(screen.getByText("DFS")).toBeInTheDocument();
    expect(screen.getByText("AI Research Terminal")).toBeInTheDocument();
  });

  it("highlights the active route via aria-current", () => {
    mockUsePathname.mockReturnValue("/dashboard/optimizer");
    render(<Sidebar />);
    expect(screen.getByText("Optimizer").closest("a")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Hitters").closest("a")).not.toHaveAttribute("aria-current");
  });

  it("marks only the exact /dashboard route as active, not every sub-route", () => {
    mockUsePathname.mockReturnValue("/dashboard/hitters");
    render(<Sidebar />);
    expect(screen.getByText("Dashboard").closest("a")).not.toHaveAttribute("aria-current");
    expect(screen.getByText("Hitters").closest("a")).toHaveAttribute("aria-current", "page");
  });

  it("collapses to an icon rail and hides labels when the collapse button is clicked", async () => {
    render(<Sidebar />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();

    await act(async () => {}); // let the mount-time hydration microtask settle first
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    await waitFor(() => expect(screen.queryByText("Dashboard")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });

  it("persists the collapsed state across remounts", async () => {
    const { unmount } = render(<Sidebar />);
    await act(async () => {}); // let the mount-time hydration microtask settle first
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    await waitFor(() => expect(window.localStorage.getItem("bigmoney-sidebar-collapsed")).toBe("1"));
    unmount();

    render(<Sidebar />);
    await waitFor(() => expect(screen.queryByText("Dashboard")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });

  it("is a properly labeled landmark for accessibility", () => {
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("carries the current ?slate= and ?date= forward on every nav link -- Milestone 32.6", () => {
    mockSearchParams = new URLSearchParams("slate=dkunofficial-152547&date=2026-08-21");
    render(<Sidebar />);
    expect(screen.getByText("Pitchers").closest("a")).toHaveAttribute(
      "href",
      "/dashboard/pitchers?slate=dkunofficial-152547&date=2026-08-21",
    );
    expect(screen.getByText("Optimizer").closest("a")).toHaveAttribute(
      "href",
      "/dashboard/optimizer?slate=dkunofficial-152547&date=2026-08-21",
    );
  });

  it("renders bare links with no query string when no slate/date is selected", () => {
    render(<Sidebar />);
    expect(screen.getByText("Hitters").closest("a")).toHaveAttribute("href", "/dashboard/hitters");
  });

  describe("M16D -- unified sport switcher (shared by MLB and NFL)", () => {
    it("always renders both MLB and NFL sport links, on an MLB page", () => {
      mockUsePathname.mockReturnValue("/dashboard");
      render(<Sidebar />);
      expect(screen.getByText("MLB").closest("a")).toHaveAttribute("href", "/dashboard");
      expect(screen.getByText("NFL").closest("a")).toHaveAttribute("href", "/nfl");
    });

    it("always renders both MLB and NFL sport links, on an NFL page", () => {
      mockUsePathname.mockReturnValue("/nfl/optimizer");
      render(<Sidebar />);
      expect(screen.getByText("MLB").closest("a")).toHaveAttribute("href", "/dashboard");
      expect(screen.getByText("NFL").closest("a")).toHaveAttribute("href", "/nfl");
    });

    it("marks MLB as the active sport on any /dashboard route", () => {
      mockUsePathname.mockReturnValue("/dashboard/optimizer");
      render(<Sidebar />);
      expect(screen.getByText("MLB").closest("a")).toHaveAttribute("aria-current", "page");
      expect(screen.getByText("NFL").closest("a")).not.toHaveAttribute("aria-current");
    });

    it("marks NFL as the active sport on any /nfl route", () => {
      mockUsePathname.mockReturnValue("/nfl/players");
      render(<Sidebar />);
      expect(screen.getByText("NFL").closest("a")).toHaveAttribute("aria-current", "page");
      expect(screen.getByText("MLB").closest("a")).not.toHaveAttribute("aria-current");
    });

    it("shows the full NFL navigation (not MLB's) once on an /nfl route", () => {
      mockUsePathname.mockReturnValue("/nfl");
      render(<Sidebar />);
      for (const label of ["Players", "Matchups", "Projections", "Optimizer", "Lineups", "Saved / Late Swap", "Usage"]) {
        expect(screen.getByText(label)).toBeInTheDocument();
      }
      // MLB-only labels must not leak into the NFL nav.
      expect(screen.queryByText("Pitchers")).not.toBeInTheDocument();
      expect(screen.queryByText("Hitters")).not.toBeInTheDocument();
      expect(screen.queryByText("Stacks")).not.toBeInTheDocument();
    });

    it("shows the full MLB navigation (not NFL's) on a /dashboard route", () => {
      mockUsePathname.mockReturnValue("/dashboard");
      render(<Sidebar />);
      expect(screen.getByText("Pitchers")).toBeInTheDocument();
      expect(screen.getByText("Hitters")).toBeInTheDocument();
      // NFL-only labels must not leak into the MLB nav.
      expect(screen.queryByText("Matchups")).not.toBeInTheDocument();
      expect(screen.queryByText("Saved / Late Swap")).not.toBeInTheDocument();
    });

    it("marks only the exact /nfl route as active among NFL items, not every nested /nfl/* route", () => {
      mockUsePathname.mockReturnValue("/nfl/players");
      render(<Sidebar />);
      expect(screen.getAllByText("Dashboard")[0].closest("a")).not.toHaveAttribute("aria-current");
      expect(screen.getByText("Players").closest("a")).toHaveAttribute("aria-current", "page");
    });

    it("carries the current ?draftGroupId= forward on every NFL nav link", () => {
      mockUsePathname.mockReturnValue("/nfl");
      mockSearchParams = new URLSearchParams("draftGroupId=151307");
      render(<Sidebar />);
      expect(screen.getByText("Players").closest("a")).toHaveAttribute("href", "/nfl/players?draftGroupId=151307");
      expect(screen.getByText("Optimizer").closest("a")).toHaveAttribute("href", "/nfl/optimizer?draftGroupId=151307");
    });

    it("does not leak MLB's ?slate=/?date= onto NFL links, or NFL's ?draftGroupId= onto MLB links", () => {
      mockUsePathname.mockReturnValue("/nfl");
      mockSearchParams = new URLSearchParams("slate=dkunofficial-152547&date=2026-08-21");
      render(<Sidebar />);
      expect(screen.getByText("Players").closest("a")).toHaveAttribute("href", "/nfl/players");
    });
  });
});
