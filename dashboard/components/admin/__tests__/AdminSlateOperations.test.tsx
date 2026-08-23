import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminSlateOperations } from "../AdminSlateOperations";

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
}

function slateRow(overrides: Record<string, unknown> = {}) {
  return {
    slateId: "dkunofficial-1", slateName: "Main", gameCount: 8, playerCount: 300,
    buildStatus: "READY", displayStatus: "READY", sourceProvenance: null, sourceHash: null,
    lastProcessedAt: null, lastRefreshedAt: null, publishedVersion: null, publishedAt: null,
    readiness: { ok: true, required: [], optional: [] }, activeJob: null,
    eligibility: null, identity: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AdminSlateOperations -- Canonical MLB Player Identity Foundation: Player Identity diagnostics", () => {
  it("renders resolved/ambiguous/unmatched counts, separate from eligibility", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow({
          identity: { dk_entries: 746, resolved: 700, ambiguous: 3, unmatched: 43 },
          eligibility: {
            raw_dk_players: 746, starting_pitchers: 16, relief_pitchers: 120, confirmed_hitters: 130,
            bench_hitters: 400, waiting_for_lineups: 30, scratched: 0, unmatched: 43, ambiguous: 3,
            optimizer_eligible: 146,
          },
        })],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("Player Identity")).toBeInTheDocument());
    expect(screen.getByText("700 / 746")).toBeInTheDocument();
    expect(screen.getByText("Player Pool Eligibility (Milestone 30.1)")).toBeInTheDocument();
  });

  it("omits the Player Identity section entirely when no match report exists yet", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow({ identity: null, eligibility: null })],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("MAIN")).toBeInTheDocument());
    expect(screen.queryByText("Player Identity")).not.toBeInTheDocument();
  });
});
