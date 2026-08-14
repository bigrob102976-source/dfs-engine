import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockGetStatus = vi.fn();
vi.mock("@/lib/externalProjectionsStatus", () => ({
  getExternalProjectionsStatus: (...args: unknown[]) => mockGetStatus(...args),
}));

import SettingsPage from "../page";

describe("SettingsPage", () => {
  it("shows BlueCollar as Waiting for API key, never exposing a credential, when unconfigured", async () => {
    mockGetStatus.mockResolvedValue({
      slate_date: "2026-08-13",
      provider: { configured_source: "unconfigured", reason: null, provider_key: null, provider_name: null, provider_version: null, is_mock: null, is_configured: false, available_providers: ["mock", "bluecollar"] },
      baseline: { exists: false, provider_name: null, is_mock: null, retrieved_at: null, player_count: null },
      adjusted: { exists: false, generated_at: null, record_count: null, adjustment_model_version: null },
    });

    const jsx = await SettingsPage();
    render(jsx);

    expect(screen.getByText("BlueCollar DFS")).toBeInTheDocument();
    expect(screen.getByText("Waiting for API key")).toBeInTheDocument();
    expect(screen.getByText("Big Money Independent")).toBeInTheDocument();
    expect(screen.getAllByText("READY")).toHaveLength(1);
    // Never render an env var VALUE, only its name as setup guidance.
    expect(screen.queryByText(/BLUECOLLAR_API_KEY=/)).not.toBeInTheDocument();
  });

  it("shows Connected with Last Updated / Slate / Players when a real provider is configured", async () => {
    mockGetStatus.mockResolvedValue({
      slate_date: "2026-08-13",
      provider: { configured_source: "explicit", reason: null, provider_key: "bluecollar", provider_name: "BlueCollar DFS", provider_version: "1.0", is_mock: false, is_configured: true, available_providers: ["mock", "bluecollar"] },
      baseline: { exists: true, provider_name: "BlueCollar DFS", is_mock: false, retrieved_at: "2026-08-13T18:00:00Z", player_count: 300 },
      adjusted: { exists: true, generated_at: "2026-08-13T19:00:00Z", record_count: 290, adjustment_model_version: "0.1.0" },
    });

    const jsx = await SettingsPage();
    render(jsx);

    expect(screen.getAllByText("Connected").length).toBeGreaterThan(0);
    expect(screen.getByText("300")).toBeInTheDocument();
  });

  it("shows MOCK EXTERNAL PROJECTIONS distinctly when the mock provider is active", async () => {
    mockGetStatus.mockResolvedValue({
      slate_date: "2026-08-13",
      provider: { configured_source: "explicit", reason: null, provider_key: "mock", provider_name: "MOCK EXTERNAL PROJECTIONS", provider_version: "mock-1.0", is_mock: true, is_configured: true, available_providers: ["mock", "bluecollar"] },
      baseline: { exists: true, provider_name: "MOCK EXTERNAL PROJECTIONS", is_mock: true, retrieved_at: "2026-08-13T18:00:00Z", player_count: 42 },
      adjusted: { exists: false, generated_at: null, record_count: null, adjustment_model_version: null },
    });

    const jsx = await SettingsPage();
    render(jsx);

    expect(screen.getByText("MOCK EXTERNAL PROJECTIONS")).toBeInTheDocument();
    expect(screen.getByText("READY (MOCK)")).toBeInTheDocument();
  });
});
