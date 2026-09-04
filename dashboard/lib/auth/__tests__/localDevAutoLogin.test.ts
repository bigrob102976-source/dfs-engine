import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Real, in-memory cookie store -- mirrors app/api/admin/sports/__tests__/
// status.test.ts's exact pattern, so establishSession()/getCurrentUser()
// exercise their REAL logic (including a real cookie round-trip)
// instead of being mocked away.
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
const { findUserByEmail, countAdmins } = await import("@/lib/db/users");
const { getCurrentUser } = await import("@/lib/auth/session");
const { isLocalDevAutoLoginEnabled, maybeAutoLoginLocalDev } = await import("../localDevAutoLogin");

const ADMIN_EMAIL = "bigrob102976@gmail.com";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  vi.unstubAllEnvs();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("isLocalDevAutoLoginEnabled -- the two-part gate", () => {
  it("true only when BOTH development AND the explicit flag are set", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");
    expect(isLocalDevAutoLoginEnabled()).toBe(true);
  });

  it("false in development with the flag unset (default-off)", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "");
    expect(isLocalDevAutoLoginEnabled()).toBe(false);
  });

  it("false in development with the flag explicitly false", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "false");
    expect(isLocalDevAutoLoginEnabled()).toBe(false);
  });

  it("false in production even with the flag set true -- production NEVER auto-logins", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");
    expect(isLocalDevAutoLoginEnabled()).toBe(false);
  });

  it("false in production with the flag unset", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "");
    expect(isLocalDevAutoLoginEnabled()).toBe(false);
  });
});

describe("maybeAutoLoginLocalDev -- production/gate safety", () => {
  it("PRODUCTION + flag=true: does nothing, no session created, no user created", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");
    // Real, documented escape hatch (lib/db/backend.ts) so this test's own
    // ASSERTIONS can query the DB under a production stub -- unrelated to,
    // and never read by, isLocalDevAutoLoginEnabled()/maybeAutoLoginLocalDev()
    // itself, whose gate is NODE_ENV alone.
    vi.stubEnv("ALLOW_SQLITE_IN_PRODUCTION", "true");

    await maybeAutoLoginLocalDev();

    expect(await getCurrentUser()).toBeNull();
    expect(await findUserByEmail(ADMIN_EMAIL)).toBeNull();
    expect(cookieStore.size).toBe(0);
  });

  it("PRODUCTION + flag=false: does nothing", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "false");

    await maybeAutoLoginLocalDev();

    expect(await getCurrentUser()).toBeNull();
    expect(cookieStore.size).toBe(0);
  });

  it("DEVELOPMENT + flag=false: does nothing, normal login still required", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "false");

    await maybeAutoLoginLocalDev();

    expect(await getCurrentUser()).toBeNull();
    expect(cookieStore.size).toBe(0);
  });

  it("DEVELOPMENT + flag=true: establishes a REAL admin session via the real session system", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");
    vi.stubEnv("LOCAL_DEV_ADMIN_EMAIL", ADMIN_EMAIL);

    await maybeAutoLoginLocalDev();

    const user = await getCurrentUser();
    expect(user).not.toBeNull();
    expect(user!.email).toBe(ADMIN_EMAIL);
    expect(user!.role).toBe("ADMIN");
    expect(cookieStore.has("bigmoney_session")).toBe(true);
    // the cookie holds an opaque random token, never anything resembling a password
    expect(cookieStore.get("bigmoney_session")).not.toContain("@");
  });

  it("is idempotent -- calling twice does not create a second user or admin", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

    await maybeAutoLoginLocalDev();
    await maybeAutoLoginLocalDev();

    expect(await countAdmins()).toBe(1);
  });

  it("never activates outside the gate even if a bootstrap user already exists (reuse-not-recreate check)", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");
    await maybeAutoLoginLocalDev(); // create + log in once
    cookieStore.clear(); // simulate a fresh browser with no cookie

    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "false"); // now disabled
    await maybeAutoLoginLocalDev();

    expect(await getCurrentUser()).toBeNull(); // no session re-issued
    expect(await countAdmins()).toBe(1); // the earlier user is untouched, not duplicated
  });
});

describe("normal production auth paths are unaffected", () => {
  it("a MEMBER role is never silently upgraded by this module existing", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");
    vi.stubEnv("ALLOW_SQLITE_IN_PRODUCTION", "true"); // test-setup escape hatch only, see the test above
    const { createUser } = await import("@/lib/db/users");
    const { hashPassword } = await import("@/lib/auth/password");
    const member = await createUser({ email: "member@example.com", passwordHash: hashPassword("whatever") });
    expect(member.role).toBe("MEMBER");

    await maybeAutoLoginLocalDev(); // production -- must not touch anything

    const { findUserById } = await import("@/lib/db/users");
    const reloaded = await findUserById(member.id);
    expect(reloaded!.role).toBe("MEMBER");
  });
});
