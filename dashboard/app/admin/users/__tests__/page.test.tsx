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

const AdminUsersPage = (await import("../page")).default;

function props(search: Record<string, string> = {}) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(search) };
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("AdminUsersPage", () => {
  it("renders every user with their subscription status", async () => {
    const user = await createUser({ email: "listed@example.com", passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    await createUser({ email: "nosub@example.com", passwordHash: "h" });

    render(await AdminUsersPage(props()));

    expect(screen.getByText("listed@example.com")).toBeInTheDocument();
    expect(screen.getByText("nosub@example.com")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("No subscription")).toBeInTheDocument();
  });

  it("applies the search filter from the query string", async () => {
    await createUser({ email: "findable@example.com", passwordHash: "h" });
    await createUser({ email: "other@example.com", passwordHash: "h" });

    render(await AdminUsersPage(props({ search: "findable" })));

    expect(screen.getByText("findable@example.com")).toBeInTheDocument();
    expect(screen.queryByText("other@example.com")).not.toBeInTheDocument();
  });

  it("shows a disabled badge for disabled accounts", async () => {
    const user = await createUser({ email: "disabled@example.com", passwordHash: "h" });
    const { setUserDisabled } = await import("@/lib/db/users");
    await setUserDisabled(user.id, true);

    render(await AdminUsersPage(props()));
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });
});
