import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Captures the actual options object passed to cookies().set() so we can
// verify the `secure` flag's production/non-production behavior directly
// -- the shared session.test.ts fake jar only records values, not options.
let lastSetOptions: Record<string, unknown> | undefined;
const cookieStore = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined),
    set: (name: string, value: string, options?: Record<string, unknown>) => {
      cookieStore.set(name, value);
      lastSetOptions = options;
    },
    delete: () => {},
  }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("../session");

const ORIGINAL_NODE_ENV = process.env.NODE_ENV;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  lastSetOptions = undefined;
});

afterEach(() => {
  vi.stubEnv("NODE_ENV", ORIGINAL_NODE_ENV ?? "test");
});

describe("session cookie security flags (fail-closed in production)", () => {
  it("sets secure:true and httpOnly:true in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    // Milestone 33.1: getExecutor() (unlike the old getDb()) re-resolves
    // the backend on its first post-reset call, so it genuinely
    // observes NODE_ENV=production here and would otherwise hit the
    // real, correct fail-closed guard (no DATABASE_URL configured in
    // this test). This test's purpose is cookie-flag behavior, not
    // database backend selection -- the documented, explicit "I
    // understand the risk" override lets it keep using local SQLite
    // under a simulated production NODE_ENV.
    vi.stubEnv("ALLOW_SQLITE_IN_PRODUCTION", "true");
    const user = await createUser({ email: "prod@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    expect(lastSetOptions?.secure).toBe(true);
    expect(lastSetOptions?.httpOnly).toBe(true);
    expect(lastSetOptions?.sameSite).toBe("lax");
  });

  it("does not force secure:true outside production (so local http:// dev still works)", async () => {
    vi.stubEnv("NODE_ENV", "test");
    const user = await createUser({ email: "dev@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    expect(lastSetOptions?.secure).toBe(false);
    expect(lastSetOptions?.httpOnly).toBe(true);
  });
});
