import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { insertSubscription } = await import("@/lib/db/subscriptions");

const AdminSubscriptionsPage = (await import("../page")).default;

function props(search: Record<string, string> = {}) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(search) };
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("AdminSubscriptionsPage", () => {
  it("renders subscriptions with user email, plan, and status", async () => {
    const user = await createUser({ email: "sub@example.com", passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });

    render(await AdminSubscriptionsPage(props()));

    expect(screen.getByText("sub@example.com")).toBeInTheDocument();
    expect(screen.getByText("Weekly")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("$10.99")).toBeInTheDocument();
    expect(screen.getByText("dev")).toBeInTheDocument();
  });

  it("shows Provider, Cancel At Period End, and Stripe IDs for a real Stripe-backed subscription", async () => {
    const user = await createUser({ email: "stripesub@example.com", passwordHash: "h" });
    const { setStripeCustomerId } = await import("@/lib/db/users");
    await setStripeCustomerId(user.id, "cus_admincheck");
    await insertSubscription({
      userId: user.id,
      planId: "monthly",
      status: "active",
      provider: "stripe",
      providerSubscriptionId: "sub_admincheck",
      cancelAtPeriodEnd: true,
    });

    render(await AdminSubscriptionsPage(props()));

    expect(screen.getByText("stripe")).toBeInTheDocument();
    expect(screen.getByText("cus_admincheck")).toBeInTheDocument();
    expect(screen.getByText("sub_admincheck")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument(); // Cancel At Period End
  });

  it("shows -- for missing Stripe customer/subscription IDs on a dev-provider row", async () => {
    const user = await createUser({ email: "devrow@example.com", passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status: "trialing" });

    render(await AdminSubscriptionsPage(props()));
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThanOrEqual(2); // customer id + subscription id
  });

  it("shows an empty state when nothing matches", async () => {
    render(await AdminSubscriptionsPage(props({ status: "active" })));
    expect(screen.getByText("No subscriptions match these filters.")).toBeInTheDocument();
  });
});
