import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RefreshPanel } from "../RefreshPanel";
import type { RunState } from "@/lib/orchestrator/types";

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
}

function stubStep(id: RunState["steps"][number]["id"], status: RunState["steps"][number]["status"] = "failed") {
  return {
    id,
    label: id,
    status,
    startedAt: null,
    finishedAt: null,
    message: id === "dfsSalaries" ? "No live DraftKings salary provider configured." : null,
    artifactPath: null,
    command: null,
    stdoutTail: null,
    stderrTail: null,
  };
}

function noProviderRun(): RunState {
  return {
    runId: "r1",
    slateDate: "2026-08-14",
    status: "failed",
    outcome: "dfs_not_connected",
    startedAt: "2026-08-14T18:00:00Z",
    finishedAt: "2026-08-14T18:00:01Z",
    currentStepId: null,
    steps: [
      { ...stubStep("research", "ready") },
      { ...stubStep("pitchers", "ready") },
      { ...stubStep("batters", "ready") },
      stubStep("dfsSalaries"),
      stubStep("playerPool", "skipped"),
      stubStep("ownership", "skipped"),
      stubStep("optimizer", "skipped"),
    ],
    slateOptions: null,
    summary: null,
    changeReport: null,
    error: "No live DraftKings salary provider configured.",
    mode: "full",
    requestedSteps: null,
  };
}

function installFetchMock(overrides: Partial<Record<string, (init?: RequestInit) => Promise<Response>>> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const impl = vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (overrides[url]) return overrides[url]!(init);
    if (url === "/api/refresh") return jsonResponse({ run: noProviderRun() });
    throw new Error(`Unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", impl);
  return { calls, impl };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RefreshPanel: no-provider-configured validation state", () => {
  it("shows the literal message and both Import CSV / Enable Mock Mode buttons", async () => {
    installFetchMock();
    render(<RefreshPanel />);

    // The literal message appears twice -- once as the failed step's own
    // message, once as the validation banner's heading -- so this checks
    // "at least one", not "exactly one".
    expect((await screen.findAllByText("No live DraftKings salary provider configured.")).length).toBeGreaterThan(0);
    expect(screen.getByText("Import CSV")).toBeInTheDocument();
    expect(screen.getByText("Enable Mock Mode")).toBeInTheDocument();
  });

  it("clicking Import CSV reveals the DraftKings CSV upload widget", async () => {
    installFetchMock();
    render(<RefreshPanel />);
    await screen.findByText(/turn on Mock Mode for development\/testing/);

    fireEvent.click(screen.getByText("Import CSV"));
    expect(await screen.findByText(/Upload DraftKings CSV/)).toBeInTheDocument();
  });

  it("clicking Enable Mock Mode POSTs the toggle then re-triggers a refresh", async () => {
    const { calls } = installFetchMock({
      "/api/settings/mock-mode": () => jsonResponse({ ok: true, enabled: true }),
      "/api/refresh": (init) => {
        if (init?.method === "POST") return jsonResponse({ run: { ...noProviderRun(), status: "running" } });
        return jsonResponse({ run: noProviderRun() });
      },
    });
    render(<RefreshPanel />);
    await screen.findByText(/turn on Mock Mode for development\/testing/);

    fireEvent.click(screen.getByText("Enable Mock Mode"));

    await waitFor(() => expect(calls.some((c) => c.url === "/api/settings/mock-mode")).toBe(true));
    const mockModeCall = calls.find((c) => c.url === "/api/settings/mock-mode")!;
    expect(JSON.parse(mockModeCall.init?.body as string)).toEqual({ enabled: true });

    await waitFor(() => expect(calls.some((c) => c.url === "/api/refresh" && c.init?.method === "POST")).toBe(true));
  });

  it("does not show the two-button state for a genuine explicit misconfiguration", async () => {
    installFetchMock({
      "/api/refresh": () =>
        jsonResponse({
          run: { ...noProviderRun(), error: "DFS_SALARY_PROVIDER='bogus' is not a recognized provider." },
        }),
    });
    render(<RefreshPanel />);

    await screen.findByText(/DFS SALARIES NOT CONNECTED/);
    expect(screen.queryByText("Import CSV")).not.toBeInTheDocument();
    expect(screen.queryByText("Enable Mock Mode")).not.toBeInTheDocument();
  });
});
