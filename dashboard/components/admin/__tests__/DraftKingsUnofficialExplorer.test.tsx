import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DraftKingsUnofficialExplorer } from "../DraftKingsUnofficialExplorer";

function installFetchMock(responses: Record<string, unknown>) {
  const fetchMock = vi.fn(async (url: string) => {
    for (const [key, body] of Object.entries(responses)) {
      if (url.includes(key)) {
        return { ok: true, json: async () => body } as Response;
      }
    }
    return { ok: false, json: async () => ({ error: "unexpected url in test" }) } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DraftKingsUnofficialExplorer", () => {
  it("shows the unofficial-data disclosure banner up front", () => {
    installFetchMock({});
    render(<DraftKingsUnofficialExplorer />);
    expect(screen.getByText(/UNOFFICIAL DRAFTKINGS DEVELOPMENT DATA/)).toBeInTheDocument();
  });

  it("never fetches on mount -- only after clicking Load Sport Data", () => {
    const fetchMock = installFetchMock({});
    render(<DraftKingsUnofficialExplorer />);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the not_enabled message honestly", async () => {
    installFetchMock({ "sport=MLB": { status: "not_enabled", detail: "Set DK_UNOFFICIAL_ENABLED=true to use this." } });
    render(<DraftKingsUnofficialExplorer />);
    fireEvent.click(screen.getByText("Load Sport Data"));
    await waitFor(() => expect(screen.getByText("Set DK_UNOFFICIAL_ENABLED=true to use this.")).toBeInTheDocument());
  });

  it("shows NO ACTIVE SLATE without treating it as an error", async () => {
    installFetchMock({ "sport=NHL": { status: "no_active_slate", sport: "NHL" } });
    render(<DraftKingsUnofficialExplorer />);
    fireEvent.change(screen.getByLabelText("Sport"), { target: { value: "NHL" } });
    fireEvent.click(screen.getByText("Load Sport Data"));
    await waitFor(() => expect(screen.getByText(/NO ACTIVE SLATE for NHL/)).toBeInTheDocument());
    expect(screen.queryByText(/Failed to load/)).not.toBeInTheDocument();
  });

  it("loads sport data and shows the slate/contest counts", async () => {
    installFetchMock({
      "sport=MLB": {
        status: "ok", sport: "MLB",
        slates: [{ draft_group_id: 152389, sport_id: 2, sport_code: "MLB", game_type_id: 2, game_type_name: "Classic", start_time: "x", tag: "Featured", label: null, game_count: 3, contest_ids: [1, 2] }],
        contests: [{ contest_id: 1, name: "X", sport_id: 2, draft_group_id: 152389, game_type: "Classic", game_type_id: 2, start_time_iso: "x", entry_fee: 5, prize_pool: 1000, max_entries: 100, current_entries: 10, is_guaranteed: true, is_starred: false }],
      },
    });
    render(<DraftKingsUnofficialExplorer />);
    fireEvent.click(screen.getByText("Load Sport Data"));
    await waitFor(() => expect(screen.getByLabelText("Slate (DraftGroup)")).toBeInTheDocument());
    expect(screen.getByText("DraftGroups").nextSibling?.textContent).toBe("1");
    expect(screen.getByText("Contests").nextSibling?.textContent).toBe("1");
  });

  it("selecting a slate loads and displays player rows in the PLAYERS tab", async () => {
    installFetchMock({
      "draftGroupId=152389": {
        status: "ok", sport: "MLB",
        slates: [{ draft_group_id: 152389, sport_id: 2, sport_code: "MLB", game_type_id: 2, game_type_name: "Classic", start_time: "x", tag: "Featured", label: null, game_count: 1, contest_ids: [1] }],
        contests: [],
        slate_detail: {
          status: "ok",
          games: [{ competition_id: 100, name: "NYY @ BAL", start_time: "x", venue: "Camden Yards", home_team: { abbreviation: "BAL" }, away_team: { abbreviation: "NYY" } }],
          draftables: [{ draftable_id: 1, display_name: "Cam Schlittler", position: "SP", salary: 11000, team_abbreviation: "NYY", status: "None", roster_slot_id: 110 }],
          roster_rules: { name: "Classic", salary_cap: 50000, roster_slots: [{ name: "P", scoring_multiplier: null }] },
          identity_match_summary: { total: 1, matched: 0, unmatched: 1, ambiguous: 0, match_percent: 0 },
          quality: {},
        },
      },
      "sport=MLB": {
        status: "ok", sport: "MLB",
        slates: [{ draft_group_id: 152389, sport_id: 2, sport_code: "MLB", game_type_id: 2, game_type_name: "Classic", start_time: "x", tag: "Featured", label: null, game_count: 1, contest_ids: [1] }],
        contests: [],
      },
    });
    render(<DraftKingsUnofficialExplorer />);
    fireEvent.click(screen.getByText("Load Sport Data"));
    await waitFor(() => expect(screen.getByLabelText("Slate (DraftGroup)")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Slate (DraftGroup)"), { target: { value: "152389" } });
    await waitFor(() => expect(screen.getByText("PLAYERS")).toBeInTheDocument());
    fireEvent.click(screen.getByText("PLAYERS"));
    expect(screen.getByText("Cam Schlittler")).toBeInTheDocument();
  });
});
