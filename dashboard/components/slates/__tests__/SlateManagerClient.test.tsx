import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}));

import { SlateManagerClient } from "../SlateManagerClient";
import type { SlateManagerRow } from "../types";

const DATE = "2026-08-17";

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
}

function row(overrides: Partial<SlateManagerRow> = {}): SlateManagerRow {
  return { slateId: "main", slateName: "Main", gameCount: 9, playerCount: 142, startTime: null, status: "READY", ...overrides };
}

beforeEach(() => {
  mockRefresh.mockClear();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SlateManagerClient", () => {
  it("shows an honest empty state when no slates are discovered", () => {
    render(<SlateManagerClient date={DATE} rows={[]} providerName={null} isMock={false} providerStatus="not_connected" />);
    expect(screen.getByText(/No slates discovered yet/)).toBeInTheDocument();
    expect(screen.getByText(/Automatic DK salary\/slate discovery is not currently available/)).toBeInTheDocument();
  });

  it("labels the source clearly: DraftKings CSV", () => {
    render(<SlateManagerClient date={DATE} rows={[row()]} providerName="draftkings_csv" isMock={false} providerStatus="ready" />);
    expect(screen.getByText("DRAFTKINGS CSV")).toBeInTheDocument();
  });

  it("labels the source clearly: MOCK -- never presented as real DraftKings data", () => {
    render(<SlateManagerClient date={DATE} rows={[row()]} providerName="mock_dev_provider" isMock providerStatus="ready" />);
    expect(screen.getByText("MOCK")).toBeInTheDocument();
  });

  it("shows each slate's status badge, games, and players", () => {
    render(
      <SlateManagerClient
        date={DATE}
        rows={[row({ slateId: "main", slateName: "Main", status: "READY" }), row({ slateId: "turbo", slateName: "Turbo", status: "MISSING", gameCount: 3, playerCount: null })]}
        providerName="draftkings_csv"
        isMock={false}
        providerStatus="ready"
      />,
    );
    expect(screen.getByText("Main")).toBeInTheDocument();
    expect(screen.getByText("Turbo")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByText("MISSING")).toBeInTheDocument();
  });

  it("Open links to the global slate selector for that slate", () => {
    render(<SlateManagerClient date={DATE} rows={[row({ slateId: "turbo" })]} providerName="draftkings_csv" isMock={false} providerStatus="ready" />);
    expect(screen.getByText("Open").closest("a")).toHaveAttribute("href", "/dashboard?slate=turbo");
  });

  it("only shows Remove Local Slate / Replace Data for DraftKings CSV slates, never for mock", () => {
    const { rerender } = render(<SlateManagerClient date={DATE} rows={[row()]} providerName="draftkings_csv" isMock={false} providerStatus="ready" />);
    expect(screen.getByText("Remove Local Slate")).toBeInTheDocument();
    expect(screen.getByText("Replace Data")).toBeInTheDocument();

    rerender(<SlateManagerClient date={DATE} rows={[row()]} providerName="mock_dev_provider" isMock providerStatus="ready" />);
    expect(screen.queryByText("Remove Local Slate")).not.toBeInTheDocument();
    expect(screen.queryByText("Replace Data")).not.toBeInTheDocument();
  });

  it("Refresh calls /api/slates/refresh with date+slateId and revalidates on success", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => jsonResponse({ status: "ready" }));
    vi.stubGlobal("fetch", impl);

    render(<SlateManagerClient date={DATE} rows={[row({ slateId: "turbo" })]} providerName="draftkings_csv" isMock={false} providerStatus="ready" />);
    fireEvent.click(screen.getByText("Refresh"));

    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
    const [url, init] = impl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/slates/refresh");
    expect(JSON.parse(init.body as string)).toEqual({ date: DATE, slateId: "turbo" });
  });

  it("Remove Local Slate finds the matching upload by label and deletes it", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
      if (url === `/api/dfs-salaries/uploads?date=${DATE}`) {
        return jsonResponse({ uploads: [{ path: "dfs_input/2026-08-17/uploaded_dk_slates/main_x.csv", slate_label: "Main" }] });
      }
      if (url === "/api/dfs-salaries/delete") return jsonResponse({ ok: true });
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", impl);

    render(<SlateManagerClient date={DATE} rows={[row({ slateId: "main", slateName: "Main" })]} providerName="draftkings_csv" isMock={false} providerStatus="ready" />);
    fireEvent.click(screen.getByText("Remove Local Slate"));

    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
    const deleteCall = impl.mock.calls.find(([url]) => url === "/api/dfs-salaries/delete")!;
    expect(JSON.parse((deleteCall[1] as RequestInit).body as string)).toEqual({ path: "dfs_input/2026-08-17/uploaded_dk_slates/main_x.csv" });
  });

  it("shows an error and does not revalidate when refresh fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ status: "error", error: "boom" }, false)));
    render(<SlateManagerClient date={DATE} rows={[row()]} providerName="draftkings_csv" isMock={false} providerStatus="ready" />);
    fireEvent.click(screen.getByText("Refresh"));

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(mockRefresh).not.toHaveBeenCalled();
  });
});
