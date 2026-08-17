import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser } = await import("@/lib/db/users");
const { insertSubscription } = await import("@/lib/db/subscriptions");

const AdminSubscriptionsPage = (await import("../page")).default;

function props(search: Record<string, string> = {}) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(search) };
}

beforeEach(() => {
  __resetDbForTests();
});

describe("AdminSubscriptionsPage", () => {
  it("renders subscriptions with user email, plan, and status", async () => {
    const user = createUser({ email: "sub@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status: "active" });

    render(await AdminSubscriptionsPage(props()));

    expect(screen.getByText("sub@example.com")).toBeInTheDocument();
    expect(screen.getByText("Weekly")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("$10.99")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", async () => {
    render(await AdminSubscriptionsPage(props({ status: "active" })));
    expect(screen.getByText("No subscriptions match these filters.")).toBeInTheDocument();
  });
});
