import { act, render, screen, waitFor } from "@testing-library/react";
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
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");

const SubscribeSuccessPage = (await import("../page")).default;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  vi.stubGlobal("fetch", vi.fn());
});

describe("SubscribeSuccessPage", () => {
  it("redirects to /login when logged out", async () => {
    await expect(SubscribeSuccessPage()).rejects.toThrow("NEXT_REDIRECT:/login?next=%2Fsubscribe%2Fsuccess");
  });

  it("shows 'Finalizing Membership...' immediately, then never grants access on its own -- only reflects real polled server state", async () => {
    const user = await createUser({ email: "polling@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ subscription: { status: "trialing" } }),
    });

    render(await SubscribeSuccessPage());
    expect(screen.getByText("Finalizing Membership...")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Trial Active")).toBeInTheDocument());
    expect(screen.getByText("WELCOME TO BIG MONEY DFS")).toBeInTheDocument();
  });

  it("shows 'Membership Active' for an active (non-trial) subscription", async () => {
    const user = await createUser({ email: "activepoll@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ subscription: { status: "active" } }),
    });

    render(await SubscribeSuccessPage());
    await waitFor(() => expect(screen.getByText("Membership Active")).toBeInTheDocument());
  });

  it("shows a graceful 'still finalizing' state (not an error) after the bounded poll window, when the webhook hasn't landed yet", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = await createUser({ email: "neverarrives@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ subscription: null }),
    });

    render(await SubscribeSuccessPage());
    expect(screen.getByText("Finalizing Membership...")).toBeInTheDocument();

    // 8 attempts * 1500ms -- advance well past the bounded window.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 9);
    });

    expect(screen.getByText(/Still finalizing/)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
