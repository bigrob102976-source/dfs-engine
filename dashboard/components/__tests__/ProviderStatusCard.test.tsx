import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProviderStatusCard } from "../ProviderStatusCard";
import type { RunSummary, StepResult } from "@/lib/orchestrator/types";

function summary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    slateDate: "2026-08-12",
    mlbGames: 15,
    dfsGames: 15,
    postedLineups: 15,
    missingLineups: 0,
    pitcherCount: 30,
    hitterCount: 270,
    salaryCoveragePercent: 100,
    positionCoveragePercent: 100,
    dkEntries: 300,
    matchedToMlb: 300,
    unmatchedCount: 0,
    rosterFeasibilityPass: true,
    ownershipReady: true,
    lineupCounts: { projection: 20, balanced: 20, leverage: 20 },
    lineupSetPaths: { projection: null, balanced: null, leverage: null },
    providerName: "mock_dev_provider",
    isMock: true,
    providerSource: "mock_explicit",
    selectedSlateId: "mock-main-2026-08-12",
    externalProjectionStatus: "not_attempted",
    externalProjectionRecordCount: null,
    ...overrides,
  };
}

function dfsStep(overrides: Partial<StepResult> = {}): StepResult {
  return {
    id: "dfsSalaries",
    label: "DFS Salaries",
    status: "ready",
    startedAt: "2026-08-12T18:00:00Z",
    finishedAt: "2026-08-12T18:01:00Z",
    message: null,
    artifactPath: null,
    command: null,
    stdoutTail: null,
    stderrTail: null,
    ...overrides,
  };
}

describe("ProviderStatusCard", () => {
  it("shows 'not checked yet' before any refresh has run", () => {
    render(<ProviderStatusCard summary={null} dfsStep={null} />);
    expect(screen.getByText(/not checked yet/i)).toBeInTheDocument();
  });

  it("shows the DEV / MOCK DATA badge when the provider is the mock fallback", () => {
    render(<ProviderStatusCard summary={summary({ isMock: true })} dfsStep={dfsStep()} />);
    expect(screen.getByText("Provider: Connected (mock_dev_provider)")).toBeInTheDocument();
    expect(screen.getByText("DEV / MOCK DATA")).toBeInTheDocument();
  });

  it("does not show the mock badge for a real (non-mock) provider", () => {
    render(<ProviderStatusCard summary={summary({ isMock: false, providerName: "real_provider", providerSource: "explicit" })} dfsStep={dfsStep()} />);
    expect(screen.queryByText("DEV / MOCK DATA")).not.toBeInTheDocument();
  });

  it("shows NOT CONNECTED when the step failed", () => {
    render(<ProviderStatusCard summary={null} dfsStep={dfsStep({ status: "failed", message: "DFS_SALARY_PROVIDER='bogus' is not a recognized provider." })} />);
    expect(screen.getByText("Provider: NOT CONNECTED")).toBeInTheDocument();
    expect(screen.getByText(/not a recognized provider/)).toBeInTheDocument();
    expect(screen.queryByText("DEV / MOCK DATA")).not.toBeInTheDocument();
  });
});
