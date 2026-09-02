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

const mockListSlates = vi.fn();
vi.mock("@/lib/optimizerWorkspace/poolCache", () => ({
  listSlates: (...args: unknown[]) => mockListSlates(...args),
}));

const { __resetDbForTests, getDb } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET } = await import("../route");

function req(query: string) {
  return new Request(`http://localhost/api/optimizer/slates${query}`);
}

async function loginAsAdmin() {
  const admin = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
}

async function loginAsMember() {
  const member = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
}

function seedCanonicalSlate(slateDate: string, providerSlateId: string) {
  getDb()
    .prepare(
      `INSERT INTO slates (
         internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc,
         game_count, game_ids_json, salary_cap, schema_version, validation_state, source_provenance, promoted_at,
         player_count, created_at, updated_at
       ) VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Main', ?, ?, 8, '[]', 50000, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', ?, 1, 'x', 'x')`,
    )
    .run(`s-${providerSlateId}`, providerSlateId, slateDate, `${slateDate}T23:05:00Z`, new Date().toISOString());
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockListSlates.mockReset();
  mockListSlates.mockResolvedValue({ status: "ready", slates: [{ slateId: "dkunofficial-legacy-today", slateName: "Main", gameCount: 8, startTime: null, gameIds: [], playerCount: 10 }], providerName: "draftkings_unofficial", isMock: false });
});

describe("M5G/M5I: /api/optimizer/slates serving-backend selection and future isolation", () => {
  it("ADMIN requesting CANONICAL_POSTGRES for today gets today's real canonical slate -- legacy listSlates never called", async () => {
    seedCanonicalSlate("2026-08-31", "dkunofficial-canary-today");
    await loginAsAdmin();

    const res = await GET(req("?date=2026-08-31&servingBackend=CANONICAL_POSTGRES"));
    const body = await res.json();
    expect(body.servingBackend).toBe("CANONICAL_POSTGRES");
    expect(body.slates.map((s: { slateId: string }) => s.slateId)).toEqual(["dkunofficial-canary-today"]);
    expect(mockListSlates).not.toHaveBeenCalled();
  });

  it("M5G: tomorrow's canonically-prefetched slate never appears in today's canonical-mode list", async () => {
    seedCanonicalSlate("2026-08-31", "dkunofficial-canary-today");
    seedCanonicalSlate("2026-09-01", "dkunofficial-canary-tomorrow");
    await loginAsAdmin();

    const res = await GET(req("?date=2026-08-31&servingBackend=CANONICAL_POSTGRES"));
    const body = await res.json();
    const slateIds = body.slates.map((s: { slateId: string }) => s.slateId);
    expect(slateIds).toContain("dkunofficial-canary-today");
    expect(slateIds).not.toContain("dkunofficial-canary-tomorrow");
  });

  it("MEMBER's CANONICAL_POSTGRES request is silently refused -- always LEGACY_R2", async () => {
    seedCanonicalSlate("2026-08-31", "dkunofficial-canary-today");
    await loginAsMember();

    const res = await GET(req("?date=2026-08-31&servingBackend=CANONICAL_POSTGRES"));
    const body = await res.json();
    expect(body.servingBackend).toBe("LEGACY_R2");
    expect(mockListSlates).toHaveBeenCalledWith("2026-08-31");
  });
});
