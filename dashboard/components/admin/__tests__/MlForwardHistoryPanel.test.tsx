import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MlForwardHistoryPanel } from "../MlForwardHistoryPanel";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MlForwardHistoryPanel", () => {
  it("shows the EARLY SAMPLE warning below the minimum slate count", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({
      history: { total_slates_completed: 2, early_sample: true, early_sample_warning: "EARLY SAMPLE -- DO NOT DRAW STRONG CONCLUSIONS", windows: { "1": { dates: ["2026-08-22"], pitchers: { source_metrics: [] }, hitters: { source_metrics: [] }, combined: { source_metrics: [] } } } },
    })));
    render(<MlForwardHistoryPanel />);
    await waitFor(() => expect(screen.getByText("EARLY SAMPLE -- DO NOT DRAW STRONG CONCLUSIONS")).toBeInTheDocument());
  });

  it("never shows the early-sample warning at or above the minimum", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({
      history: { total_slates_completed: 5, early_sample: false, early_sample_warning: null, windows: { "5": { dates: [], pitchers: { source_metrics: [] }, hitters: { source_metrics: [] }, combined: { source_metrics: [] } }, all: { dates: [], pitchers: { source_metrics: [] }, hitters: { source_metrics: [] }, combined: { source_metrics: [] } } } },
    })));
    render(<MlForwardHistoryPanel />);
    await waitFor(() => expect(screen.getByText("5 slate(s) completed")).toBeInTheDocument());
    expect(screen.queryByText(/EARLY SAMPLE/)).not.toBeInTheDocument();
  });

  it("only renders window buttons for windows that actually exist", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({
      history: {
        total_slates_completed: 3, early_sample: true, early_sample_warning: "EARLY SAMPLE -- DO NOT DRAW STRONG CONCLUSIONS",
        windows: {
          "1": { dates: [], pitchers: { source_metrics: [] }, hitters: { source_metrics: [] }, combined: { source_metrics: [] } },
          "3": { dates: [], pitchers: { source_metrics: [] }, hitters: { source_metrics: [] }, combined: { source_metrics: [] } },
          all: { dates: [], pitchers: { source_metrics: [] }, hitters: { source_metrics: [] }, combined: { source_metrics: [] } },
        },
      },
    })));
    render(<MlForwardHistoryPanel />);
    await waitFor(() => expect(screen.getByText("Last 1")).toBeInTheDocument());
    expect(screen.getByText("Last 3")).toBeInTheDocument();
    expect(screen.queryByText("Last 5")).not.toBeInTheDocument();
    expect(screen.queryByText("Last 10")).not.toBeInTheDocument();
  });

  it("shows a friendly message when zero slates are completed", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ history: { total_slates_completed: 0, early_sample: true, early_sample_warning: "EARLY SAMPLE -- DO NOT DRAW STRONG CONCLUSIONS", windows: {} } })));
    render(<MlForwardHistoryPanel />);
    await waitFor(() => expect(screen.getByText(/No completed slates yet/)).toBeInTheDocument());
  });
});
