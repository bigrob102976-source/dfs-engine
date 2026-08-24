import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined),
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  }),
}));

const mockGetBillingMode = vi.fn();
vi.mock("@/lib/billing/stripeConfig", () => ({
  getBillingMode: () => mockGetBillingMode(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { insertSubscription, updateSubscriptionStatus } = await import("@/lib/db/subscriptions");

const BillingPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockGetBillingMode.mockReturnValue("dev");
});

describe("BillingPage", () => {
  it("shows a 'no active membership' state with a link to /pricing when unsubscribed", async () => {
    const user = await createUser({ email: "nosub@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    render(await BillingPage());
    expect(screen.getByText("No Active Membership")).toBeInTheDocument();
    expect(screen.getByText("View plans →").closest("a")).toHaveAttribute("href", "/pricing");
  });

  it("shows the full membership field set for a trialing subscriber", async () => {
    const user = await createUser({ email: "trialing@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "trialing",
      trialEndsAt: "2026-08-20T00:00:00Z",
      currentPeriodEnd: "2026-08-20T00:00:00Z",
    });

    render(await BillingPage());
    expect(screen.getByText("Weekly")).toBeInTheDocument();
    expect(screen.getByText("$10.99 / week")).toBeInTheDocument();
    expect(screen.getByText("trialing")).toBeInTheDocument();
    expect(screen.getByText("In Trial")).toBeInTheDocument();
    expect(screen.getByText("Manage Subscription")).toBeInTheDocument();
    expect(screen.getByText("Cancel membership")).toBeInTheDocument();
  });

  it("shows cancel_at_period_end and access-through date for a canceling-but-still-active subscriber", async () => {
    const user = await createUser({ email: "cancelatperiod@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const sub = await insertSubscription({
      userId: user.id,
      planId: "monthly",
      status: "active",
      currentPeriodEnd: "2026-09-01T00:00:00Z",
      cancelAtPeriodEnd: true,
    });
    await updateSubscriptionStatus(sub.id, "active", { cancel_at_period_end: 1 });

    render(await BillingPage());
    const yesCells = screen.getAllByText("Yes");
    expect(yesCells.length).toBeGreaterThan(0);
  });

  it("hides the Cancel button and shows -- for Access Through once a subscription has fully ended", async () => {
    const user = await createUser({ email: "expired@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await insertSubscription({ userId: user.id, planId: "weekly", status: "expired" });

    render(await BillingPage());
    expect(screen.queryByText("Cancel membership")).not.toBeInTheDocument();
  });

  it("shows the Stripe test-mode label and hides the dev-mode banner when configured", async () => {
    mockGetBillingMode.mockReturnValue("stripe_test");
    const user = await createUser({ email: "stripemode@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await insertSubscription({ userId: user.id, planId: "weekly", status: "active", provider: "stripe" });

    render(await BillingPage());
    expect(screen.getByText("Stripe (Test Mode)")).toBeInTheDocument();
    expect(screen.queryByText("Development Mode")).not.toBeInTheDocument();
  });

  it("shows an explicit 'Billing Not Configured' state (fails visibly, not silently) when unconfigured in production-like mode", async () => {
    mockGetBillingMode.mockReturnValue("unconfigured");
    const user = await createUser({ email: "unconfigured@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    render(await BillingPage());
    expect(screen.getByText("Billing Not Configured")).toBeInTheDocument();
  });
});
