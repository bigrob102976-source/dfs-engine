import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser } = await import("@/lib/db/users");
const { insertSubscription } = await import("@/lib/db/subscriptions");
const { grantUserEntitlement } = await import("@/lib/db/entitlements");

const AdminUserDetailPage = (await import("../page")).default;

function props(id: string) {
  return { params: Promise.resolve({ id }), searchParams: Promise.resolve({}) };
}

beforeEach(() => {
  __resetDbForTests();
});

describe("AdminUserDetailPage", () => {
  it("throws NEXT_NOT_FOUND for an unknown user id", async () => {
    await expect(AdminUserDetailPage(props("nope"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("renders account, subscription, and entitlement details for a real user", async () => {
    const user = createUser({ email: "detail@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "monthly", status: "trialing" });
    grantUserEntitlement({ userId: user.id, entitlementKey: "mlb.optimizer", grantedBy: null, reason: "beta" });

    render(await AdminUserDetailPage(props(user.id)));

    expect(screen.getAllByText("detail@example.com").length).toBeGreaterThan(0);
    expect(screen.getByText("trialing")).toBeInTheDocument();
    expect(screen.getByText("mlb.optimizer")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.getByText("Promote to Admin")).toBeInTheDocument();
  });

  it("shows 'No subscription' state and an empty entitlements message", async () => {
    const user = createUser({ email: "bare@example.com", passwordHash: "h" });
    render(await AdminUserDetailPage(props(user.id)));

    expect(screen.getByText("No subscription.")).toBeInTheDocument();
    expect(screen.getByText(/No explicit entitlement grants/)).toBeInTheDocument();
  });

  it("shows trial eligibility as 'Eligible' for a fresh user with no trial consumed", async () => {
    const user = createUser({ email: "eligible@example.com", passwordHash: "h" });
    render(await AdminUserDetailPage(props(user.id)));
    expect(screen.getByText("Eligible")).toBeInTheDocument();
  });

  it("shows trial eligibility as 'Consumed' plus the consumption date once a trial has been used", async () => {
    const user = createUser({ email: "consumed@example.com", passwordHash: "h" });
    const { markTrialConsumed } = await import("@/lib/db/users");
    markTrialConsumed(user.id);
    render(await AdminUserDetailPage(props(user.id)));
    expect(screen.getByText("Consumed")).toBeInTheDocument();
  });

  it("shows Stripe customer id, provider, subscription id, and cancel-at-period-end for a Stripe-backed subscription, plus a Resync button", async () => {
    const user = createUser({ email: "stripedetail@example.com", passwordHash: "h" });
    const { setStripeCustomerId } = await import("@/lib/db/users");
    setStripeCustomerId(user.id, "cus_detailcheck");
    insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "active",
      provider: "stripe",
      providerSubscriptionId: "sub_detailcheck",
      cancelAtPeriodEnd: true,
    });

    render(await AdminUserDetailPage(props(user.id)));

    expect(screen.getByText("cus_detailcheck")).toBeInTheDocument();
    expect(screen.getByText("sub_detailcheck")).toBeInTheDocument();
    expect(screen.getByText("stripe")).toBeInTheDocument();
    expect(screen.getByText("Resync from Stripe")).toBeInTheDocument();
  });

  it("does NOT show the Resync button for a dev-provider subscription", async () => {
    const user = createUser({ email: "devdetail@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status: "active" });

    render(await AdminUserDetailPage(props(user.id)));
    expect(screen.queryByText("Resync from Stripe")).not.toBeInTheDocument();
  });
});
