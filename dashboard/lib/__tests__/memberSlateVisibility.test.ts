import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

const { __resetDbForTests, getDb } = await import("../db/client");
const { __resetExecutorForTests } = await import("../db/executor");
const { createUser, updateUserRole } = await import("../db/users");
const { establishSession } = await import("../auth/session");
const { filterSlatesForCurrentViewer } = await import("../memberSlateVisibility");

function opt(slateId: string, provider?: string) {
  return { slateId, slateName: slateId, gameCount: 1, startTime: null, gameIds: [], playerCount: 10, provider };
}

function insertPublished(slateDate: string, slateId: string) {
  getDb()
    .prepare(
      "INSERT INTO slate_status (id, slate_date, slate_id, status, published_version, created_at, updated_at) VALUES (?, ?, ?, 'PUBLISHED', 1, 'x', 'x')",
    )
    .run(`ss-${slateId}`, slateDate, slateId);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

afterEach(() => {
  cookieStore.clear();
});

describe("BREAK-GLASS ADMIN CSV UPLOAD Phase 8 -- member slate visibility", () => {
  it("an unauthenticated/member viewer sees only PUBLISHED slates, unchanged from before this feature", async () => {
    insertPublished("2026-09-04", "152904");
    const slates = [opt("152904", "draftkings_unofficial"), opt("999999", "draftkings_unofficial")];
    const visible = await filterSlatesForCurrentViewer(slates, "2026-09-04");
    expect(visible.map((s) => s.slateId)).toEqual(["152904"]);
  });

  it("a draftkings_csv slate is excluded from a MEMBER viewer even if it were somehow marked published", async () => {
    const member = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
    await establishSession(member.id, null);
    insertPublished("2026-09-04", "dkcsv-main-2026-09-04");

    const slates = [opt("dkcsv-main-2026-09-04", "draftkings_csv")];
    const visible = await filterSlatesForCurrentViewer(slates, "2026-09-04");
    expect(visible).toEqual([]);
  });

  it("a draftkings_csv slate is excluded from an unauthenticated viewer the same way", async () => {
    insertPublished("2026-09-04", "dkcsv-main-2026-09-04");
    const slates = [opt("dkcsv-main-2026-09-04", "draftkings_csv")];
    const visible = await filterSlatesForCurrentViewer(slates, "2026-09-04");
    expect(visible).toEqual([]);
  });

  it("ADMIN sees every slate, including draftkings_csv ones, regardless of publish state", async () => {
    const admin = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
    await updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);

    const slates = [opt("dkcsv-main-2026-09-04", "draftkings_csv"), opt("152904", "draftkings_unofficial")];
    const visible = await filterSlatesForCurrentViewer(slates, "2026-09-04");
    expect(visible.map((s) => s.slateId).sort()).toEqual(["152904", "dkcsv-main-2026-09-04"]);
  });
});
