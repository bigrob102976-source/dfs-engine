import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExternalProjectionsStatusCard } from "../ExternalProjectionsStatusCard";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ExternalProjectionsStatusCard", () => {
  it("shows BlueCollar DFS WAITING FOR API ACCESS by default (unconfigured)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          slate_date: "2026-08-13",
          provider: { configured_source: "unconfigured", reason: null, provider_key: null, provider_name: null, is_mock: null, is_configured: false },
          baseline: { exists: false, provider_name: null, is_mock: null, retrieved_at: null, player_count: null },
          adjusted: { exists: false, generated_at: null, record_count: null, adjustment_model_version: null },
        }),
      ),
    );
    render(<ExternalProjectionsStatusCard />);
    await waitFor(() => expect(screen.getByText("BlueCollar DFS")).toBeInTheDocument());
    expect(screen.getByText("WAITING FOR API ACCESS")).toBeInTheDocument();
    expect(screen.getByText("Big Money Independent")).toBeInTheDocument();
    expect(screen.getAllByText("READY")).toHaveLength(1); // only Big Money Independent
  });

  it("shows BlueCollar DFS WAITING FOR API ACCESS even when explicitly configured (still undocumented)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          slate_date: "2026-08-13",
          provider: { configured_source: "explicit", reason: null, provider_key: "bluecollar", provider_name: "BlueCollar DFS", is_mock: false, is_configured: false },
          baseline: { exists: false, provider_name: null, is_mock: null, retrieved_at: null, player_count: null },
          adjusted: { exists: false, generated_at: null, record_count: null, adjustment_model_version: null },
        }),
      ),
    );
    render(<ExternalProjectionsStatusCard />);
    await waitFor(() => expect(screen.getByText("WAITING FOR API ACCESS")).toBeInTheDocument());
    // Never an error state.
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });

  it("shows MOCK EXTERNAL PROJECTIONS as READY and clearly distinct from BlueCollar", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          slate_date: "2026-08-13",
          provider: { configured_source: "explicit", reason: null, provider_key: "mock", provider_name: "MOCK EXTERNAL PROJECTIONS", is_mock: true, is_configured: true },
          baseline: { exists: true, provider_name: "MOCK EXTERNAL PROJECTIONS", is_mock: true, retrieved_at: "2026-08-13T18:00:00Z", player_count: 42 },
          adjusted: { exists: true, generated_at: "2026-08-13T19:00:00Z", record_count: 40, adjustment_model_version: "0.1.0" },
        }),
      ),
    );
    render(<ExternalProjectionsStatusCard />);
    await waitFor(() => expect(screen.getByText("MOCK EXTERNAL PROJECTIONS")).toBeInTheDocument());
    expect(screen.queryByText("BlueCollar DFS")).not.toBeInTheDocument();
    expect(screen.getAllByText("READY")).toHaveLength(2); // mock provider + Big Money Independent
  });

  it("never renders anything resembling an API key even if a malformed response included one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          slate_date: "2026-08-13",
          provider: {
            configured_source: "explicit", reason: null, provider_key: "bluecollar", provider_name: "BlueCollar DFS", is_mock: false, is_configured: false,
            // A malicious/buggy backend response including a key -- the
            // component only ever destructures known-safe fields, so this
            // must never reach the DOM.
            api_key: "sk-should-never-render-12345",
          },
          baseline: { exists: false, provider_name: null, is_mock: null, retrieved_at: null, player_count: null },
          adjusted: { exists: false, generated_at: null, record_count: null, adjustment_model_version: null },
        }),
      ),
    );
    render(<ExternalProjectionsStatusCard />);
    await waitFor(() => expect(screen.getByText("WAITING FOR API ACCESS")).toBeInTheDocument());
    expect(screen.queryByText(/sk-should-never-render/)).not.toBeInTheDocument();
  });
});
