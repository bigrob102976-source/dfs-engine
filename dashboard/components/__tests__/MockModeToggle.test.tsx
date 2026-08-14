import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MockModeToggle } from "../MockModeToggle";

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MockModeToggle", () => {
  it("renders OFF by default and shows the off state", () => {
    render(<MockModeToggle initialEnabled={false} />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/OFF \(default\)/)).toBeInTheDocument();
  });

  it("renders DEV MODE text when initially enabled", () => {
    render(<MockModeToggle initialEnabled={true} />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/DEV MODE -- Mock Mode is ON/)).toBeInTheDocument();
  });

  it("toggling posts the new state and updates the UI", async () => {
    const impl = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => jsonResponse({ status: "ok", enabled: true }));
    vi.stubGlobal("fetch", impl);

    render(<MockModeToggle initialEnabled={false} />);
    fireEvent.click(screen.getByRole("switch"));

    await waitFor(() => expect(impl).toHaveBeenCalled());
    const [url, init] = impl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/settings/mock-mode");
    expect(JSON.parse(init.body as string)).toEqual({ enabled: true });

    expect(await screen.findByText(/DEV MODE -- Mock Mode is ON/)).toBeInTheDocument();
  });

  it("shows an error and leaves state unchanged when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ error: "Unexpected failure setting Mock Mode." })));

    render(<MockModeToggle initialEnabled={false} />);
    fireEvent.click(screen.getByRole("switch"));

    expect(await screen.findByText("Unexpected failure setting Mock Mode.")).toBeInTheDocument();
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });
});
