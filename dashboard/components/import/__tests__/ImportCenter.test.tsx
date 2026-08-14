import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImportCenter } from "../ImportCenter";

const DATE = "2026-08-13";

const ANALYSIS_RESULT = {
  headers: ["Player", "Team", "Salary", "Proj"],
  detected_mapping: { name: "Player", team: "Team", salary: "Salary", projection: "Proj" },
  resolved_mapping: { name: "Player", team: "Team", salary: "Salary", projection: "Proj" },
  preview_rows: [{ Player: "Ace Pitcher", Team: "TOR", Salary: "9000", Proj: "20.5" }],
  parse_warnings: [],
  validation: {
    players_imported: 1,
    matched: 1,
    unmatched: 0,
    ambiguous: 0,
    duplicate_players: 0,
    missing_salary: 0,
    missing_projection: 0,
    missing_position: 0,
    unknown_teams: [],
    unknown_opponents: [],
    needs_review: [],
  },
  importable_player_count: 1,
  skipped_missing_name: 0,
  skipped_missing_projection: 0,
};

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function installFetchMock(overrides: Partial<Record<string, (init?: RequestInit) => Promise<Response>>> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const impl = vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (overrides[url]) return overrides[url]!(init);
    if (url.startsWith("/api/import/history")) return jsonResponse({ imports: [] });
    if (url === "/api/import/analyze") return jsonResponse(ANALYSIS_RESULT);
    throw new Error(`Unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", impl);
  return { calls, impl };
}

function csvFile(name = "bluecollar.csv"): File {
  return new File(["Player,Team,Salary,Proj\nAce Pitcher,TOR,9000,20.5\n"], name, { type: "text/csv" });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ImportCenter", () => {
  it("loads import history for the given date on mount", async () => {
    const { calls } = installFetchMock();
    render(<ImportCenter date={DATE} />);
    await waitFor(() => expect(calls.some((c) => c.url === `/api/import/history?date=${DATE}`)).toBe(true));
    expect(await screen.findByText(/No CSV imports for this date yet/i)).toBeInTheDocument();
  });

  it("rejects a non-.csv file client-side without calling analyze", async () => {
    installFetchMock();
    render(<ImportCenter date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const badFile = new File(["not a csv"], "projections.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [badFile] } });

    expect(await screen.findByText(/Only \.csv files are supported/i)).toBeInTheDocument();
  });

  it("analyzes an uploaded CSV and renders the preview, mapping, and validation summary", async () => {
    const { calls } = installFetchMock();
    render(<ImportCenter date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });

    await waitFor(() => expect(calls.some((c) => c.url === "/api/import/analyze")).toBe(true));
    expect(await screen.findByText("Ace Pitcher")).toBeInTheDocument();
    expect(screen.getByText(/Import 1 Player/)).toBeInTheDocument();

    const analyzeCall = calls.find((c) => c.url === "/api/import/analyze")!;
    const form = analyzeCall.init?.body as FormData;
    expect(form.get("provider")).toBe("bluecollar");
    expect(form.get("date")).toBe(DATE);
    expect((form.get("file") as File).name).toBe("bluecollar.csv");
  });

  it("re-analyzes with a manual mapping override when the user edits a mapping select", async () => {
    const { calls } = installFetchMock();
    render(<ImportCenter date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });
    await screen.findByText("Ace Pitcher");

    const opponentSelect = screen.getByLabelText(/Opponent/i) as HTMLSelectElement;
    fireEvent.change(opponentSelect, { target: { value: "Team" } });

    await waitFor(() => expect(calls.filter((c) => c.url === "/api/import/analyze")).toHaveLength(2));
    const secondCall = calls.filter((c) => c.url === "/api/import/analyze")[1];
    const form = secondCall.init?.body as FormData;
    expect(JSON.parse(form.get("mapping") as string)).toEqual({ opponent: "Team" });
  });

  it("imports the CSV, shows the success screen, and refreshes history", async () => {
    let historyCallCount = 0;
    const { calls } = installFetchMock({
      "/api/import/history": () => {
        historyCallCount += 1;
        return jsonResponse({ imports: historyCallCount > 1 ? [{ path: "p.json", provider_name: "BlueCollar DFS", retrieved_at: "2026-08-13T18:00:00Z", player_count: 1, matched: 1, unmatched: 0, is_active: true }] : [] });
      },
      "/api/import/save": () =>
        jsonResponse({
          status: "ready",
          path: "external_projection_snapshots/2026-08-13/provider_bluecollar_20260813T180000.json",
          player_count: 1,
          provider_name: "BlueCollar DFS",
          validation_summary: { matched: 1 },
          adjustment: { status: "ready", record_count: 1 },
        }),
    });

    render(<ImportCenter date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });
    await screen.findByText("Ace Pitcher");

    fireEvent.click(screen.getByText(/Import 1 Player/));

    expect(await screen.findByText("Import Successful")).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.url.startsWith("/api/import/history"))).toHaveLength(2));
  });

  it("shows an error and does not clear the form when the save fails", async () => {
    installFetchMock({
      "/api/import/save": () => jsonResponse({ status: "no_players", reason: "No row had both a name and a projection." }),
    });

    render(<ImportCenter date={DATE} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [csvFile()] } });
    await screen.findByText("Ace Pitcher");

    fireEvent.click(screen.getByText(/Import 1 Player/));

    expect(await screen.findByText("No row had both a name and a projection.")).toBeInTheDocument();
    expect(screen.queryByText("Import Successful")).not.toBeInTheDocument();
  });
});
