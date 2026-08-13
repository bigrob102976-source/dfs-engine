import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

import { MissingDataState } from "../MissingDataState";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function baseStep(id: string, label: string, status: string) {
  return { id, label, status, startedAt: null, finishedAt: null, message: null, artifactPath: null, command: null, stdoutTail: null, stderrTail: null };
}

function runningRun() {
  return {
    runId: "r1",
    slateDate: "2026-08-13",
    status: "running",
    outcome: null,
    startedAt: "2026-08-13T12:00:00Z",
    finishedAt: null,
    currentStepId: "batters",
    steps: [baseStep("research", "Research Package", "ready"), baseStep("batters", "Batter Agent", "running")],
    slateOptions: null,
    summary: null,
    changeReport: null,
    error: null,
    mode: "smart",
    requestedSteps: ["batters"],
  };
}

function completedRun() {
  return { ...runningRun(), status: "completed", currentStepId: null, steps: [baseStep("research", "Research Package", "ready"), baseStep("batters", "Batter Agent", "ready")] };
}

function failedRun() {
  return {
    ...runningRun(),
    status: "failed",
    outcome: "batter_agent_failure",
    error: "Batter Agent exited non-zero.",
    steps: [baseStep("research", "Research Package", "ready"), baseStep("batters", "Batter Agent", "failed")],
  };
}

beforeEach(() => {
  refreshMock.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("MissingDataState", () => {
  it("renders the friendly empty state with no developer command visible", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => jsonResponse({ run: null })),
    );
    render(
      <MissingDataState
        title="Batter research is not ready"
        description="Generate today's hitter research to view projections and Statcast analysis."
        primaryActionLabel="Generate Batter Research"
        targetSteps={["batters"]}
      />,
    );
    expect(screen.getByText("Batter research is not ready")).toBeInTheDocument();
    expect(screen.getByText("Generate Batter Research")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
  });

  it("clicking the primary action POSTs the exact targetSteps with smart:true", async () => {
    const impl = vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/refresh" && !init) return jsonResponse({ run: null });
      if (url === "/api/refresh" && init?.method === "POST") return jsonResponse({ run: runningRun() });
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", impl);
    render(
      <MissingDataState title="t" description="d" primaryActionLabel="Generate Batter Research" targetSteps={["batters"]} />,
    );
    fireEvent.click(screen.getByText("Generate Batter Research"));

    await waitFor(() => expect(screen.getByText("Batter Agent")).toBeInTheDocument());

    const postCall = impl.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall).toBeTruthy();
    const body = JSON.parse((postCall![1] as RequestInit).body as string);
    expect(body).toEqual({ targetSteps: ["batters"], smart: true });
  });

  it("shows live per-step progress while the run is active", async () => {
    const impl = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return jsonResponse({ run: runningRun() });
      return jsonResponse({ run: null });
    });
    vi.stubGlobal("fetch", impl);
    render(<MissingDataState title="t" description="d" primaryActionLabel="Generate Batter Research" targetSteps={["batters"]} />);
    fireEvent.click(screen.getByText("Generate Batter Research"));

    await waitFor(() => expect(screen.getByText("Generating...")).toBeInTheDocument());
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
  });

  it("revalidates the page (router.refresh) once the run completes, without a manual browser refresh", async () => {
    let pollCount = 0;
    const impl = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return jsonResponse({ run: runningRun() });
      pollCount += 1;
      return jsonResponse({ run: pollCount >= 2 ? completedRun() : runningRun() });
    });
    vi.stubGlobal("fetch", impl);
    render(<MissingDataState title="t" description="d" primaryActionLabel="Generate Batter Research" targetSteps={["batters"]} />);
    fireEvent.click(screen.getByText("Generate Batter Research"));

    await waitFor(() => expect(refreshMock).toHaveBeenCalledTimes(1), { timeout: 10000 });
  }, 15000);

  it("calls a caller-supplied onReady instead of router.refresh when provided", async () => {
    const onReady = vi.fn();
    const impl = vi.fn((_url: string, init?: RequestInit) => jsonResponse({ run: init?.method === "POST" ? completedRun() : null }));
    vi.stubGlobal("fetch", impl);
    render(<MissingDataState title="t" description="d" primaryActionLabel="Prepare Optimizer Data" targetSteps={["pitchers", "batters"]} onReady={onReady} />);
    fireEvent.click(screen.getByText("Prepare Optimizer Data"));

    await waitFor(() => expect(onReady).toHaveBeenCalledTimes(1));
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("shows a failure message and a Try Again action when the run fails", async () => {
    const impl = vi.fn((_url: string, init?: RequestInit) => jsonResponse({ run: init?.method === "POST" ? failedRun() : null }));
    vi.stubGlobal("fetch", impl);
    render(<MissingDataState title="Batter research is not ready" description="d" primaryActionLabel="Generate Batter Research" targetSteps={["batters"]} />);
    fireEvent.click(screen.getByText("Generate Batter Research"));

    await waitFor(() => expect(screen.getByText("Try Again")).toBeInTheDocument());
    expect(screen.getByText("Batter Agent exited non-zero.")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
  });
});
