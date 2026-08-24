import { beforeEach, describe, expect, it, vi } from "vitest";

// Minimal in-memory fake of the next/headers cookies() jar -- only the
// get/set/delete surface lib/auth/session.ts actually calls. next/headers
// requires a real Next.js request context, which Vitest's jsdom
// environment doesn't provide, so this is mocked the same way this
// module would be exercised inside a real Route Handler/Server Action.
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
const { createUser, updateUserRole, setUserDisabled } = await import("@/lib/db/users");
const { establishSession, getCurrentUser, destroySession, SESSION_COOKIE } = await import("../session");

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("session", () => {
  it("getCurrentUser returns null when no cookie is set", async () => {
    expect(await getCurrentUser()).toBeNull();
  });

  it("establishSession + getCurrentUser round-trips to the right user", async () => {
    const user = await createUser({ email: "s@example.com", passwordHash: "h" });
    await establishSession(user.id, "test-agent");
    const current = await getCurrentUser();
    expect(current?.id).toBe(user.id);
    expect(current?.email).toBe("s@example.com");
  });

  it("role is always read fresh from the DB, never cached from establishSession time", async () => {
    const user = await createUser({ email: "r@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    expect((await getCurrentUser())?.role).toBe("MEMBER");

    await updateUserRole(user.id, "ADMIN");
    expect((await getCurrentUser())?.role).toBe("ADMIN");
  });

  it("destroySession clears the cookie and invalidates the session", async () => {
    const user = await createUser({ email: "d@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await destroySession();
    expect(await getCurrentUser()).toBeNull();
    expect(cookieStore.has(SESSION_COOKIE)).toBe(false);
  });

  it("a forged/tampered cookie value resolves to no user (client-side manipulation attempt)", async () => {
    cookieStore.set(SESSION_COOKIE, "forged-token-value-that-was-never-issued");
    expect(await getCurrentUser()).toBeNull();
  });

  it("a disabled account's session no longer resolves", async () => {
    const user = await createUser({ email: "disabled@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    expect(await getCurrentUser()).not.toBeNull();

    await setUserDisabled(user.id, true);
    expect(await getCurrentUser()).toBeNull();
  });
});
