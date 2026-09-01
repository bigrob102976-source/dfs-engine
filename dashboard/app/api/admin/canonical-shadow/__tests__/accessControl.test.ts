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

const { __resetDbForTests, getDb } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET: getCanonicalShadowStatus } = await import("../route");

async function loginAsAdmin() {
  const admin = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

async function loginAsMember() {
  const member = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
  return member;
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("M3J -- canonical shadow admin monitor access control", () => {
  it("401s with no session", async () => {
    const res = await getCanonicalShadowStatus();
    expect(res.status).toBe(401);
  });

  it("403s for a logged-in MEMBER -- members must never see shadow ingestion internals", async () => {
    await loginAsMember();
    const res = await getCanonicalShadowStatus();
    expect(res.status).toBe(403);
  });

  it("200s for an ADMIN and returns real slate/review-queue data", async () => {
    await loginAsAdmin();
    getDb()
      .prepare(
        "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_date, first_game_start_utc, schema_version, validation_state, created_at, updated_at) VALUES ('s1','MLB','draftkings','draftkings_unofficial','152904','2026-08-31','2026-08-31T23:05:00Z','slate_normalized_v1','VALID','x','x')",
      )
      .run();

    const res = await getCanonicalShadowStatus();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body.slates)).toBe(true);
    expect(body.slates[0].provider_slate_id).toBe("152904");
    expect(Array.isArray(body.reviewQueue)).toBe(true);
  });

  it("never returns a database URL, Railway variable, API key, or storage credential", async () => {
    await loginAsAdmin();
    process.env.DATABASE_URL_TEST_SENTINEL = "postgres://sentinel-should-never-appear";
    const res = await getCanonicalShadowStatus();
    const bodyText = await res.text();
    for (const forbidden of ["DATABASE_URL", "RAILWAY_", "OBJECT_STORAGE_", "sentinel-should-never-appear", "AWS_SECRET", "STRIPE_SECRET"]) {
      expect(bodyText).not.toContain(forbidden);
    }
    delete process.env.DATABASE_URL_TEST_SENTINEL;
  });
});
