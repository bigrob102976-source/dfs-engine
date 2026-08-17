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

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");

const SubscribeCanceledPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

describe("SubscribeCanceledPage", () => {
  it("redirects to /login when logged out", async () => {
    await expect(SubscribeCanceledPage()).rejects.toThrow("NEXT_REDIRECT:/login?next=%2Fsubscribe%2Fcanceled");
  });

  it("explains the checkout was canceled and no changes were made, with a link back to pricing", async () => {
    const user = createUser({ email: "canceledpage@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    render(await SubscribeCanceledPage());
    expect(screen.getByText("Checkout Canceled")).toBeInTheDocument();
    expect(screen.getByText(/No subscription changes were made/)).toBeInTheDocument();
    expect(screen.getByText("Return to Pricing").closest("a")).toHaveAttribute("href", "/pricing");
  });
});
