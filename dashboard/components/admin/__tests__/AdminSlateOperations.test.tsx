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
    blueCollarCoverage: { returned: 0, usable: 0, identityResolved: 0, eligible: 0, optimizerReady: 0 },
    changeReport: null,
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

describe("AdminSlateOperations -- M32.7: BlueCollar Coverage diagnostics", () => {
  it("renders returned/usable/identity-resolved/eligible/optimizer-ready as separate counts", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow({
          blueCollarCoverage: { returned: 746, usable: 159, identityResolved: 415, eligible: 20, optimizerReady: 20 },
        })],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("BlueCollar Coverage")).toBeInTheDocument());
    expect(screen.getByText("746")).toBeInTheDocument();
    expect(screen.getByText("159")).toBeInTheDocument();
    expect(screen.getByText("415")).toBeInTheDocument();
    // 20 appears twice (Eligible and Optimizer-Ready coincide in this
    // architecture -- see computeBlueCollarCoverage's own docstring).
    expect(screen.getAllByText("20").length).toBe(2);
  });

  it("omits the BlueCollar Coverage section when BlueCollar has returned nothing for this slate", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow()],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("MAIN")).toBeInTheDocument());
    expect(screen.queryByText("BlueCollar Coverage")).not.toBeInTheDocument();
  });
});

describe("AdminSlateOperations -- M32.7: Admin Change Report", () => {
  it("renders the real change counts from the last refresh, using actual results", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow({
          changeReport: {
            lineupsPosted: 2, hittersBecameEligible: 18, starterChanged: 1,
            nativeGenerated: 18, aiGenerated: 18, mlGenerated: 18, stacksBecameReady: 2,
            unchanged: ["Vegas", "Weather", "BlueCollar"],
          },
        })],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("Last Refresh Changes")).toBeInTheDocument());
    expect(screen.getByText("2 lineups posted")).toBeInTheDocument();
    expect(screen.getByText("18 hitters became eligible")).toBeInTheDocument();
    expect(screen.getByText("1 starter changed")).toBeInTheDocument();
    expect(screen.getByText("No Change: Vegas, Weather, BlueCollar")).toBeInTheDocument();
  });

  it("shows a clean 'no change' message when a refresh changed nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow({
          changeReport: {
            lineupsPosted: 0, hittersBecameEligible: 0, starterChanged: 0,
            nativeGenerated: 0, aiGenerated: 0, mlGenerated: 0, stacksBecameReady: 0,
            unchanged: ["Vegas", "Weather", "BlueCollar"],
          },
        })],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("No change from the last refresh.")).toBeInTheDocument());
  });

  it("omits the change report block when no refresh has completed yet", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      jsonResponse({
        date: "2026-08-23", providerName: "DRAFTKINGS_UNOFFICIAL_LIVE", isMock: false,
        slates: [slateRow({ changeReport: null })],
        recentOperations: [],
      }),
    ));

    render(<AdminSlateOperations date="2026-08-23" />);

    await waitFor(() => expect(screen.getByText("MAIN")).toBeInTheDocument());
    expect(screen.queryByText("Last Refresh Changes")).not.toBeInTheDocument();
  });
});
