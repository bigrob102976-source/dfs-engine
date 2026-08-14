import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  usePathname: () => "/dashboard",
}));

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let originalRoot: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-responsive-test";
  vi.stubGlobal(
    "fetch",
    vi.fn(() => jsonResponse({ run: null })),
  );
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Desktop-first responsive layout is expressed as Tailwind breakpoint
 * classes (md:/lg:) directly in markup -- jsdom can't emulate a real
 * viewport, so these tests assert the responsive classes are actually
 * present on the key grid containers rather than rendering at a given
 * width. */
describe("Responsive layout", () => {
  it("the main dashboard's top metric row collapses from 2 to 6 columns across breakpoints", async () => {
    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage();
    const { container } = render(jsx);
    const topRow = container.querySelector(".grid.grid-cols-2");
    expect(topRow).toBeTruthy();
    expect(topRow?.className).toContain("md:grid-cols-3");
    expect(topRow?.className).toContain("lg:grid-cols-6");
  });

  it("the dashboard's slate-highlights grid adapts from 1 to 3 columns", async () => {
    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage();
    const { container } = render(jsx);
    const highlightsGrid = container.querySelector(".grid.grid-cols-1.gap-3.md\\:grid-cols-2.lg\\:grid-cols-3");
    expect(highlightsGrid).toBeTruthy();
  });
});
