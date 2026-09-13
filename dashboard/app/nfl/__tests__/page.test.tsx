import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import fixture from "./fixtures/nflSlate153068.json";

// The dashboard is a client component that loads through useNflData.
// These tests drive it with a REAL production payload (DraftGroup
// 153068, captured 2026-09-13) rather than a hand-written fixture, so a
// field the backend actually emits as null cannot be papered over by an
// optimistic mock. This does NOT replace verifying the rendered page in
// a browser -- it exists to catch a runtime crash during client render,
// which typecheck cannot see and which would leave the page blank in
// production.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  usePathname: () => "/nfl",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/nfl/useNflDraftGroupId", () => ({
  useNflDraftGroupId: () => 153068,
}));

vi.mock("@/components/nfl/NflPageShell", () => ({
  NflPageShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const useNflData = vi.fn();
vi.mock("@/lib/nfl/useNflData", () => ({
  useNflData: (id: number | null) => useNflData(id),
}));

import NflDashboardPage from "../page";

function withData(data: unknown) {
  useNflData.mockReturnValue({ data, loading: false, error: null, refresh: vi.fn() });
}

describe("NFL dashboard", () => {
  it("renders every headline card from a real production payload", () => {
    withData(fixture);
    render(<NflDashboardPage />);

    for (const title of [
      "Highest Game Total",
      "Lowest Game Total",
      "Highest Implied Team Total",
      "Best QB",
      "Best RB",
      "Best WR",
      "Best TE",
      "Best DST",
      "Top Cash Play",
      "Top GPP Play",
      "Top Value",
      "Top Leverage",
      "Highest Owned",
      "Best QB Stack (QB + pass catcher)",
      "Best Game Stack (QB + 2 + bring-back)",
      "Slate Readiness",
      "Top Plays by Position",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(screen.getByText(/Injury Watch/)).toBeInTheDocument();
  });

  it("shows real Vegas numbers rather than blanks when odds are present", () => {
    withData(fixture);
    render(<NflDashboardPage />);
    // The captured slate is fully priced, so the totals must be real.
    const highest = Math.max(...fixture.games.map((g) => g.total ?? Number.NEGATIVE_INFINITY));
    expect(screen.getAllByText(highest.toFixed(1)).length).toBeGreaterThan(0);
  });

  it("renders honest statuses instead of zeros when Vegas is missing", () => {
    const noVegas = {
      ...fixture,
      vegas_configured: false,
      vegas_source_provenance: "not_configured",
      games: fixture.games.map((g) => ({
        ...g,
        total: null,
        spread_home: null,
        home_implied_total: null,
        away_implied_total: null,
      })),
      players: fixture.players.map((p) => ({ ...p, matchup: null })),
    };
    withData(noVegas);
    render(<NflDashboardPage />);
    expect(screen.getAllByText("AWAITING VEGAS").length).toBeGreaterThan(0);
    // A missing total must never render as a 0.
    expect(screen.queryByText("0.0")).toBeNull();
  });

  it("renders AWAITING PROJECTION rather than ranking players on nothing", () => {
    const noProjections = {
      ...fixture,
      players: fixture.players.map((p) => ({ ...p, projection: null, ownership: null })),
      projection_coverage: {},
      ownership_generated: 0,
    };
    withData(noProjections);
    render(<NflDashboardPage />);
    expect(screen.getAllByText("AWAITING PROJECTION").length).toBeGreaterThan(0);
  });

  it("does not crash when the slate has no players at all", () => {
    withData({ ...fixture, players: [], games: [], game_count: 0, player_count: 0 });
    expect(() => render(<NflDashboardPage />)).not.toThrow();
  });
});
