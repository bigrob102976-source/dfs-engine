import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/nfl",
  useSearchParams: () => new URLSearchParams(),
}));

import NflLayout from "../layout";

/** NFL public access -- this layout must NEVER redirect, for anyone.
 * Unlike the prior admin-only/member-only versions, it has no
 * auth/session/DB dependency at all, so this test needs none either.
 *
 * M16D: the layout now also renders the shared Sidebar shell (sport
 * switcher + NFL nav). Since Sidebar makes no auth check and fetches no
 * data, this stays true even with the shell present -- verified below
 * by rendering the layout with no session/cookie/DB mock of any kind. */
describe("NFL workspace layout access", () => {
  it("renders children for a completely anonymous visitor -- never redirects", () => {
    const result = NflLayout({ children: "content" as unknown as React.ReactNode });
    expect(result).toBeTruthy();
  });

  it("renders the shared sport-switcher sidebar (MLB and NFL links) alongside the page content, still with no auth check", () => {
    render(<NflLayout>{"nfl page content"}</NflLayout>);
    expect(screen.getByText("MLB").closest("a")).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText("NFL").closest("a")).toHaveAttribute("href", "/nfl");
    expect(screen.getByText("nfl page content")).toBeInTheDocument();
  });

  it("marks NFL as the active sport in the shared sidebar", () => {
    render(<NflLayout>{"content"}</NflLayout>);
    expect(screen.getByText("NFL").closest("a")).toHaveAttribute("aria-current", "page");
  });
});
