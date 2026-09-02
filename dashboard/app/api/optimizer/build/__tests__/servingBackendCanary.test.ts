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

const mockBuildLineups = vi.fn();
vi.mock("@/lib/optimizerWorkspace/buildRunner", () => ({
  buildLineups: (...args: unknown[]) => mockBuildLineups(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { setFeatureFlagState } = await import("@/lib/db/featureFlags");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { CANONICAL_SERVING_FLAG_KEY } = await import("@/lib/servingBackend/config");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/optimizer/build", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}

function baseBody(overrides: Record<string, unknown> = {}) {
  return { slateId: "dkunofficial-canary", lineups: 1, ...overrides };
}

async function loginAsAdmin() {
  const user = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(user.id, "ADMIN");
  await establishSession(user.id, null);
  return user;
}

async function loginAsMember() {
  const user = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(user.id, null);
  return user;
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockBuildLineups.mockReset();
  mockBuildLineups.mockResolvedValue({
    ok: true, errors: [], coverage: null, lineupSetPath: "x.json", csvPath: "x.csv", lineupsRequested: 1, lineupsGenerated: 1,
    stoppedReason: null, lineups: [], elapsedMs: 10, excludedMissingProjectionSource: [],
  });
});

describe("M6K: /api/optimizer/build serving-backend authorization -- never trusts the client", () => {
  it("ADMIN's explicit CANONICAL_POSTGRES request is honored -- buildLineups receives the authorized backend", async () => {
    await loginAsAdmin();
    const res = await POST(req(baseBody({ servingBackend: "CANONICAL_POSTGRES" })));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.servingBackend).toBe("CANONICAL_POSTGRES");
    expect(mockBuildLineups).toHaveBeenCalledWith(expect.objectContaining({ servingBackend: "CANONICAL_POSTGRES" }));
  });

  it("MEMBER's CANONICAL_POSTGRES request is silently downgraded to LEGACY_R2 -- no privilege escalation", async () => {
    await loginAsMember();
    const res = await POST(req(baseBody({ servingBackend: "CANONICAL_POSTGRES" })));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.servingBackend).toBe("LEGACY_R2");
    expect(mockBuildLineups).toHaveBeenCalledWith(expect.objectContaining({ servingBackend: "LEGACY_R2" }));
  });

  it("omitting servingBackend is the production default -- LEGACY_R2 for ADMIN too", async () => {
    await loginAsAdmin();
    const res = await POST(req(baseBody()));
    const body = await res.json();
    expect(body.servingBackend).toBe("LEGACY_R2");
  });

  it("M6P rollback: once the flag is DISABLED, an ADMIN's build request immediately reverts to LEGACY_R2 -- no code change, no redeploy", async () => {
    await loginAsAdmin();
    const before = await POST(req(baseBody({ servingBackend: "CANONICAL_POSTGRES" })));
    expect((await before.json()).servingBackend).toBe("CANONICAL_POSTGRES");

    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "DISABLED", null);

    const after = await POST(req(baseBody({ servingBackend: "CANONICAL_POSTGRES" })));
    expect((await after.json()).servingBackend).toBe("LEGACY_R2");
  });
});
