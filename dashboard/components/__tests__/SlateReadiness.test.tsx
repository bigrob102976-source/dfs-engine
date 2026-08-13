import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

import { SlateReadiness } from "../SlateReadiness";
import type { ArtifactReadiness } from "@/lib/orchestrator/artifactStatus";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

const ALL_READY: ArtifactReadiness = {
  research: true,
  pitchers: true,
  batters: true,
  dfsSalaries: true,
  playerPool: true,
  ownership: true,
  optimizer: true,
};

const ONLY_HITTERS_MISSING: ArtifactReadiness = { ...ALL_READY, batters: false };

beforeEach(() => {
  refreshMock.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SlateReadiness", () => {
  it("shows ALL SYSTEMS READY and no refresh button when everything is ready", () => {
    render(<SlateReadiness readiness={ALL_READY} />);
    expect(screen.getByText("ALL SYSTEMS READY")).toBeInTheDocument();
    expect(screen.queryByText("Refresh Missing Data")).not.toBeInTheDocument();
    expect(screen.getAllByText("READY")).toHaveLength(7);
  });

  it("shows a READY/MISSING row per step and a Refresh Missing Data button when something is missing", () => {
    render(<SlateReadiness readiness={ONLY_HITTERS_MISSING} />);
    expect(screen.queryByText("ALL SYSTEMS READY")).not.toBeInTheDocument();
    expect(screen.getByText("Refresh Missing Data")).toBeInTheDocument();
    expect(screen.getByText("Hitters")).toBeInTheDocument();
    expect(screen.getAllByText("READY")).toHaveLength(6);
    expect(screen.getAllByText("MISSING")).toHaveLength(1);
  });

  it("clicking Refresh Missing Data starts a smart refresh targeting the full optimizer chain", async () => {
    const impl = vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/refresh" && init?.method === "POST") {
        return jsonResponse({
          run: {
            runId: "r1",
            slateDate: "2026-08-13",
            status: "running",
            outcome: null,
            startedAt: "2026-08-13T12:00:00Z",
            finishedAt: null,
            currentStepId: "batters",
            steps: [{ id: "batters", label: "Batter Agent", status: "running", startedAt: null, finishedAt: null, message: null, artifactPath: null, command: null, stdoutTail: null, stderrTail: null }],
            slateOptions: null,
            summary: null,
            changeReport: null,
            error: null,
            mode: "smart",
            requestedSteps: ["optimizer"],
          },
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", impl);
    render(<SlateReadiness readiness={ONLY_HITTERS_MISSING} />);
    fireEvent.click(screen.getByText("Refresh Missing Data"));

    await waitFor(() => expect(screen.getByText("RUNNING")).toBeInTheDocument());
    const body = JSON.parse((impl.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ targetSteps: ["optimizer"], smart: true });
  });

  it("does not show any developer CLI text", () => {
    render(<SlateReadiness readiness={ONLY_HITTERS_MISSING} />);
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });
});
