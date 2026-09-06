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

// Real redirect() throws a special NEXT_REDIRECT error Next's rendering
// machinery intercepts -- outside a real request we fake the same
// "throws with the destination attached" contract, mirroring
// lib/auth/__tests__/guards.test.ts.
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const NflLayout = (await import("../layout")).default;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

/** NFL production access fix -- proves the real access rule end-to-end
 * through the real guard/session/DB stack (not a mocked guard), the
 * same discipline lib/auth/__tests__/guards.test.ts already uses for
 * requireAuth/requireAdmin themselves. */
describe("NFL workspace layout access", () => {
  it("redirects an anonymous request to /login", async () => {
    await expect(NflLayout({ children: null })).rejects.toThrow("NEXT_REDIRECT:/login");
  });

  it("allows a real, ordinary MEMBER through -- no admin role required", async () => {
    const user = await createUser({ email: "nfl-member@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const result = await NflLayout({ children: "content" as unknown as React.ReactNode });
    expect(result).toBeTruthy();
  });

  it("allows a real ADMIN through too", async () => {
    const user = await createUser({ email: "nfl-admin@example.com", passwordHash: "h" });
    await updateUserRole(user.id, "ADMIN");
    await establishSession(user.id, null);
    const result = await NflLayout({ children: "content" as unknown as React.ReactNode });
    expect(result).toBeTruthy();
  });
});
