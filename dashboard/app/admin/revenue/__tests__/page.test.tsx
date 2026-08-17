import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetBillingMode = vi.fn();
vi.mock("@/lib/billing/stripeConfig", () => ({
  getBillingMode: () => mockGetBillingMode(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser } = await import("@/lib/db/users");
const { insertSubscription } = await import("@/lib/db/subscriptions");

const AdminRevenuePage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  mockGetBillingMode.mockReturnValue("dev");
});

describe("AdminRevenuePage", () => {
  it("shows -- for Refunds and Churn Rate, never a fabricated number", async () => {
    render(await AdminRevenuePage());

    expect(screen.getByText("Refunds")).toBeInTheDocument();
    expect(screen.getByText("Churn Rate")).toBeInTheDocument();
    // A third "--" is expected too: Trial Conversion is also genuinely
    // uncalculable (0/0) on an empty system, not just Refunds/Churn.
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBe(3);
    expect(screen.getByText(/does not yet track payment refunds/)).toBeInTheDocument();
  });

  it("shows the new subscriber-count cards required for spec parity", async () => {
    const user = createUser({ email: "revenuecard@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status: "active" });

    render(await AdminRevenuePage());
    expect(screen.getByText("Active Subscribers")).toBeInTheDocument();
    expect(screen.getByText("Weekly Subscribers")).toBeInTheDocument();
    expect(screen.getByText("Monthly Subscribers")).toBeInTheDocument();
    expect(screen.getByText("Trialing")).toBeInTheDocument();
    expect(screen.getByText("Past Due")).toBeInTheDocument();
    expect(screen.getByText("Canceled")).toBeInTheDocument();
  });

  it("shows the Stripe test-mode disclosure when configured", async () => {
    mockGetBillingMode.mockReturnValue("stripe_test");
    render(await AdminRevenuePage());
    expect(screen.getByText(/Stripe is connected in TEST MODE/)).toBeInTheDocument();
  });

  it("shows the unconfigured disclosure without fabricating a mode", async () => {
    mockGetBillingMode.mockReturnValue("unconfigured");
    render(await AdminRevenuePage());
    expect(screen.getByText(/Billing is not configured/)).toBeInTheDocument();
  });
});
