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

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { insertSubscription } = await import("@/lib/db/subscriptions");

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("AccountPage", () => {
  it("renders profile fields and 'no active membership' when there is no subscription", async () => {
    const user = await createUser({ email: "profile@example.com", passwordHash: "h", displayName: "Test Member" });
    await establishSession(user.id, null);

    const AccountPage = (await import("../page")).default;
    render(await AccountPage());

    expect(screen.getByText("profile@example.com")).toBeInTheDocument();
    expect(screen.getByText("Test Member")).toBeInTheDocument();
    expect(screen.getByText("MEMBER")).toBeInTheDocument();
    expect(screen.getByText(/No active membership/)).toBeInTheDocument();
  });

  it("renders subscription details when one exists", async () => {
    const user = await createUser({ email: "sub@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "trialing",
      trialEndsAt: "2026-08-20T00:00:00Z",
      currentPeriodEnd: "2026-08-20T00:00:00Z",
    });

    const AccountPage = (await import("../page")).default;
    render(await AccountPage());

    expect(screen.getByText("Weekly")).toBeInTheDocument();
    expect(screen.getByText("trialing")).toBeInTheDocument();
  });

  it("shows MLB as LIVE and other sports as Coming Soon", async () => {
    const user = await createUser({ email: "sports@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    const AccountPage = (await import("../page")).default;
    render(await AccountPage());

    expect(screen.getByText("MLB")).toBeInTheDocument();
    expect(screen.getByText(/NFL/)).toBeInTheDocument();
    expect(screen.getAllByText(/Coming Soon/).length).toBe(3);
  });
});
