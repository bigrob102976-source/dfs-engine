import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}));

const { ResyncSubscriptionButton } = await import("../ResyncSubscriptionButton");

beforeEach(() => {
  mockRefresh.mockClear();
  vi.stubGlobal("fetch", vi.fn());
});

describe("ResyncSubscriptionButton", () => {
  it("POSTs to the resync endpoint and refreshes the page on success", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    render(<ResyncSubscriptionButton subscriptionId="sub-row-id" />);

    fireEvent.click(screen.getByText("Resync from Stripe"));

    expect(fetch).toHaveBeenCalledWith("/api/admin/subscriptions/sub-row-id/resync", { method: "POST" });
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
  });

  it("shows an error message and does not refresh when the request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, json: async () => ({ error: "Failed to resync from Stripe." }) });
    render(<ResyncSubscriptionButton subscriptionId="sub-row-id" />);

    fireEvent.click(screen.getByText("Resync from Stripe"));

    expect(await screen.findByText("Failed to resync from Stripe.")).toBeInTheDocument();
    expect(mockRefresh).not.toHaveBeenCalled();
  });
});
