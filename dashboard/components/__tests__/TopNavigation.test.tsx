import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}));

import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { TopNavigation } from "../TopNavigation";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

beforeEach(() => {
  mockRefresh.mockClear();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }) as unknown as typeof window.matchMedia;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderTopNav(overrides: Partial<Parameters<typeof TopNavigation>[0]> = {}) {
  return render(
    <ThemeProvider>
      <TopNavigation slateLabel="Today · 2026-08-14" user={{ email: "member@example.com", isAdmin: false }} {...overrides} />
    </ThemeProvider>,
  );
}

describe("TopNavigation", () => {
  it("renders the current slate indicator", () => {
    renderTopNav();
    expect(screen.getByText("Today · 2026-08-14")).toBeInTheDocument();
  });

  it("renders an optional rightSlot for page-specific controls (e.g. Optimizer's Projection Source)", () => {
    renderTopNav({ rightSlot: <span>Projection Source</span> });
    expect(screen.getByText("Projection Source")).toBeInTheDocument();
  });

  it("renders the theme toggle", () => {
    renderTopNav();
    expect(screen.getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
  });

  it("renders search content passed in via the search prop", () => {
    renderTopNav({ search: <input placeholder="Search any player..." /> });
    expect(screen.getByPlaceholderText("Search any player...")).toBeInTheDocument();
  });

  it("notifications menu opens and shows an honest empty state", () => {
    renderTopNav();
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    expect(screen.getByText("No new notifications.")).toBeInTheDocument();
  });

  it("profile menu shows the signed-in email, an Account link, and a sign-out action", () => {
    renderTopNav();
    fireEvent.click(screen.getByRole("button", { name: "Profile" }));
    expect(screen.getByText("member@example.com")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Account" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
  });

  it("hides the Admin Panel link for a non-admin user", () => {
    renderTopNav({ user: { email: "member@example.com", isAdmin: false } });
    fireEvent.click(screen.getByRole("button", { name: "Profile" }));
    expect(screen.queryByRole("menuitem", { name: "Admin Panel" })).not.toBeInTheDocument();
  });

  it("shows the Admin Panel link for an admin user", () => {
    renderTopNav({ user: { email: "admin@example.com", isAdmin: true } });
    fireEvent.click(screen.getByRole("button", { name: "Profile" }));
    expect(screen.getByRole("menuitem", { name: "Admin Panel" })).toHaveAttribute("href", "/admin");
  });

  it("the sign-out form posts to /api/auth/logout", () => {
    renderTopNav();
    fireEvent.click(screen.getByRole("button", { name: "Profile" }));
    const form = screen.getByRole("menuitem", { name: "Sign out" }).closest("form");
    expect(form).toHaveAttribute("action", "/api/auth/logout");
  });

  it("refresh button POSTs to /api/refresh and revalidates once the run completes", async () => {
    let pollCount = 0;
    const impl = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return jsonResponse({ run: { status: "running" } });
      pollCount += 1;
      return jsonResponse({ run: { status: pollCount >= 2 ? "completed" : "running" } });
    });
    vi.stubGlobal("fetch", impl);
    renderTopNav();

    fireEvent.click(screen.getByRole("button", { name: "Refresh today's slate" }));
    await waitFor(() => expect(mockRefresh).toHaveBeenCalledTimes(1), { timeout: 10000 });
    const postCall = impl.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall?.[0]).toBe("/api/refresh");
  }, 15000);
});
