import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuickActionsPanel } from "../QuickActionsPanel";

const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

beforeEach(() => {
  refreshMock.mockClear();
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ run: null })));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const EXPECTED_LINKS: Array<[string, string]> = [
  ["Build Lineups", "/dashboard/optimizer"],
  ["Top Hitters", "/dashboard/hitters"],
  ["Top Pitchers", "/dashboard/pitchers"],
  ["Stacks", "/dashboard/stacks"],
  ["Ownership", "/dashboard/ownership"],
  ["Weather", "/dashboard/environment"],
  ["Vegas", "/dashboard/vegas"],
  ["Yesterday", "/dashboard/yesterday"],
  ["History", "/dashboard/history"],
  ["Portfolio", "/dashboard/portfolio"],
  ["Import Projections", "/dashboard/import"],
];

describe("QuickActionsPanel", () => {
  it("links every quick action to its existing page -- never a new/duplicated view", () => {
    render(<QuickActionsPanel />);
    for (const [label, href] of EXPECTED_LINKS) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
  });

  it("Weather points at the real Game Environment data, not the dead-end placeholder page", () => {
    render(<QuickActionsPanel />);
    expect(screen.getByRole("link", { name: "Weather" })).toHaveAttribute("href", "/dashboard/environment");
  });

  it("Refresh Research posts a smart, targeted refresh (pitchers/batters only) and revalidates", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => jsonResponse({ run: null }));
    vi.stubGlobal("fetch", impl);
    render(<QuickActionsPanel />);

    fireEvent.click(screen.getByText("Refresh Research"));

    await vi.waitFor(() => expect(impl).toHaveBeenCalled());
    const [url, init] = impl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/refresh");
    expect(JSON.parse(init.body as string)).toEqual({ targetSteps: ["pitchers", "batters"], smart: true });
    await vi.waitFor(() => expect(refreshMock).toHaveBeenCalled());
  });
});
