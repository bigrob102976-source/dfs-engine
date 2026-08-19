import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

import { Sidebar } from "../Sidebar";

beforeEach(() => {
  window.localStorage.clear();
  mockUsePathname.mockReturnValue("/dashboard");
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
});
