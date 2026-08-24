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

const mockRedirect = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT:${url}`);
});
vi.mock("next/navigation", () => ({
  redirect: (url: string) => mockRedirect(url),
}));

const mockGetBillingMode = vi.fn().mockReturnValue("dev");
vi.mock("@/lib/billing/stripeConfig", () => ({
  getBillingMode: () => mockGetBillingMode(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { insertSubscription } = await import("@/lib/db/subscriptions");

const SubscribePage = (await import("../page")).default;

function props(search: Record<string, string> = {}) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(search) };
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockRedirect.mockClear();
});

describe("SubscribePage", () => {
  it("redirects to /login with a next= pointing back to /subscribe (preserving ?plan=) when logged out", async () => {
    await expect(SubscribePage(props({ plan: "weekly" }))).rejects.toThrow(
      "NEXT_REDIRECT:/login?next=%2Fsubscribe%3Fplan%3Dweekly",
    );
  });

  it("shows both plan picker cards for a logged-in user with no subscription", async () => {
    const user = await createUser({ email: "picker@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    render(await SubscribePage(props()));
    expect(screen.getByText("Choose Your Plan")).toBeInTheDocument();
    expect(screen.getByText("Weekly")).toBeInTheDocument();
    expect(screen.getByText("Monthly")).toBeInTheDocument();
  });

  it("shows an 'already a member' state instead of the plan picker for an active subscriber", async () => {
    const user = await createUser({ email: "already@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await insertSubscription({ userId: user.id, planId: "weekly", status: "trialing" });

    render(await SubscribePage(props()));
    expect(screen.getByText(/already a member/i)).toBeInTheDocument();
    expect(screen.queryByText("Choose Your Plan")).not.toBeInTheDocument();
  });

  it("still shows the plan picker for a user whose subscription is canceled (no remaining access)", async () => {
    const user = await createUser({ email: "canceled@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const sub = await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    const { cancelSubscription } = await import("@/lib/db/subscriptions");
    await cancelSubscription(sub.id);

    render(await SubscribePage(props()));
    expect(screen.getByText("Choose Your Plan")).toBeInTheDocument();
  });
});
