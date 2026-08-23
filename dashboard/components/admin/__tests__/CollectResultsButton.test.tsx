import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}));

import { CollectResultsButton } from "../CollectResultsButton";

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
}

afterEach(() => {
  vi.unstubAllGlobals();
  mockRefresh.mockReset();
});

describe("CollectResultsButton", () => {
  it("POSTs date/slateId and refreshes on success", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ status: { status: "partial" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CollectResultsButton date="2026-08-22" slateId="dkunofficial-152547" />);

    fireEvent.click(screen.getByText("Collect Results"));
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());

    expect(fetchMock).toHaveBeenCalledWith("/api/admin/ml-forward-results/collect", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ date: "2026-08-22", slateId: "dkunofficial-152547" }),
    }));
  });

  it("shows an error message and never refreshes when the API call fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ error: "boom" }, false)));
    render(<CollectResultsButton date="2026-08-22" slateId="dkunofficial-152547" />);

    fireEvent.click(screen.getByText("Collect Results"));
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
    expect(mockRefresh).not.toHaveBeenCalled();
  });
});
