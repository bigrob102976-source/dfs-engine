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

const mockLoadPool = vi.fn();
vi.mock("@/lib/optimizerWorkspace/poolCache", () => ({
  loadPool: (...args: unknown[]) => mockLoadPool(...args),
}));

const { __resetDbForTests, getDb } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { setFeatureFlagState } = await import("@/lib/db/featureFlags");
const { createUser, findUserById, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { CANONICAL_SERVING_FLAG_KEY } = await import("@/lib/servingBackend/config");
const { POST } = await import("../route");

/** M5I/M5J -- this is the real, end-to-end admin-canary proof: a genuine
 * canonical Postgres row is seeded, the real HTTP route handler is
 * invoked (not a mocked resolveServingBackend), and the real DB-backed
 * feature flag (seeded ADMIN_ONLY by migrations/0012 (SQLite) /
 * migrations-postgres/0013) is what actually decides the outcome --
 * mirrors dashboard/lib/servingBackend/canonicalPostgresBackend.test.ts's
 * own fixture convention. */

function req(body: unknown) {
  return new Request("http://localhost/api/optimizer/pool", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}

async function loginAsAdmin() {
  const admin = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return (await findUserById(admin.id))!;
}

async function loginAsMember() {
  const member = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
  return member;
}

function seedCanonicalSlate() {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         game_count, game_ids_json, salary_cap, schema_version, validation_state, source_provenance, promoted_at,
         player_count, created_at, updated_at
       ) VALUES ('canary-s1', 'MLB', 'draftkings', 'draftkings_unofficial', 'dkunofficial-canary', 'Main', '2026-08-31', '2026-08-31T23:05:00Z', 8, '[]', 50000, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', ?, 1, 'x', 'x')`,
    )
    .run(new Date().toISOString());
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES ('canary-s1', '1', 'Canary Player', 'BOS', 'TOR', 4500, '["OF"]', 'UNRESOLVED', 'x', 'x')`,
    )
    .run();
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockLoadPool.mockReset();
  mockLoadPool.mockResolvedValue({ date: "2026-08-31", slateId: "dkunofficial-canary", players: [], providerSource: "draftkings_unofficial_live" });
});

describe("M5I/M5J: admin canary -- real end-to-end serving-backend selection", () => {
  it("ADMIN requesting CANONICAL_POSTGRES gets a real canonical-served pool -- legacy loadPool is never called", async () => {
    seedCanonicalSlate();
    const admin = await loginAsAdmin();

    const res = await POST(req({ slateId: "dkunofficial-canary", date: "2026-08-31", servingBackend: "CANONICAL_POSTGRES" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.servingBackend).toBe("CANONICAL_POSTGRES");
    expect(body.pool.players).toHaveLength(1);
    expect(body.pool.players[0].name).toBe("Canary Player");
    expect(body.pool.players[0].salary).toBe(4500);
    expect(mockLoadPool).not.toHaveBeenCalled();
    void admin;
  });

  it("MEMBER's identical CANONICAL_POSTGRES request is silently refused -- always LEGACY_R2, no override possible", async () => {
    seedCanonicalSlate();
    await loginAsMember();

    const res = await POST(req({ slateId: "dkunofficial-canary", date: "2026-08-31", servingBackend: "CANONICAL_POSTGRES" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.servingBackend).toBe("LEGACY_R2");
    expect(mockLoadPool).toHaveBeenCalledWith("2026-08-31", "dkunofficial-canary", false);
  });

  it("omitting servingBackend entirely is the production default -- LEGACY_R2 for ADMIN too", async () => {
    seedCanonicalSlate();
    await loginAsAdmin();

    const res = await POST(req({ slateId: "dkunofficial-canary", date: "2026-08-31" }));
    const body = await res.json();
    expect(body.servingBackend).toBe("LEGACY_R2");
    expect(mockLoadPool).toHaveBeenCalled();
  });

  it("M5L rollback: flipping the flag to DISABLED instantly reverts even an in-flight ADMIN canonical request to LEGACY_R2 -- no code change, no redeploy, no data loss", async () => {
    seedCanonicalSlate();
    const admin = await loginAsAdmin();
    void admin;

    const before = await POST(req({ slateId: "dkunofficial-canary", date: "2026-08-31", servingBackend: "CANONICAL_POSTGRES" }));
    expect((await before.json()).servingBackend).toBe("CANONICAL_POSTGRES");

    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "DISABLED", null);

    const after = await POST(req({ slateId: "dkunofficial-canary", date: "2026-08-31", servingBackend: "CANONICAL_POSTGRES" }));
    expect((await after.json()).servingBackend).toBe("LEGACY_R2");

    // The canonical row itself is untouched by the rollback -- rolling
    // back never deletes canonical data (M5 rule #10).
    const row = getDb().prepare("SELECT COUNT(*) as c FROM slates WHERE provider_slate_id = 'dkunofficial-canary'").get() as { c: number };
    expect(row.c).toBe(1);
  });

  it("canonical mode surfaces an honest unavailable error rather than a fabricated pool when no canonical row exists", async () => {
    // No seedCanonicalSlate() call -- genuinely absent.
    await loginAsAdmin();
    const res = await POST(req({ slateId: "dkunofficial-canary", date: "2026-08-31", servingBackend: "CANONICAL_POSTGRES" }));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toMatch(/not found/);
    expect(mockLoadPool).not.toHaveBeenCalled();
  });
});
