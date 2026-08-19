import fs from "node:fs";
import os from "node:os";
import path from "node:path";
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

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getPublishedVersion, getSlateStatus, listPublishedSlateIds, upsertSlateStatus } = await import("@/lib/db/slateStatus");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { POST: publishSlate } = await import("../publish/route");
const { POST: unpublishSlate } = await import("../unpublish/route");
const { POST: archiveSlate } = await import("../archive/route");

let tmpDir: string;
const DATE = "2026-08-19";
const SLATE_ID = "dkcsv-main-2026-08-19";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function req(body: unknown) {
  return new Request("http://localhost/x", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

async function loginAsAdmin() {
  const admin = createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

async function loginAsMember() {
  const member = createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
  return member;
}

function makeSlateReady() {
  writeJson(`dfs_input/${DATE}/dk_player_pool_1.json`, {
    selected_slate_id: SLATE_ID, player_count: 1,
    players: [{ dk_player_id: "d1", mlb_player_id: "h1", name: "X", team: "AAA", player_type: "hitter" }],
  });
  writeJson(`dfs_input/${DATE}/dk_match_report_1.json`, {
    dk_entries: 1, dk_games_total: 1, dk_games_matched_to_research: 1, source_provenance: "OFFICIAL_USER_UPLOAD",
    identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
  });
  writeJson(`native_projection_snapshots/${DATE}/native_projection_1.json`, {
    slate_date: DATE, generated_at: "x", model_version: "1.0.0", player_count: 1,
    players: [{ player_id: "h1", name: "X", team: "AAA", player_type: "hitter" }], warnings: [],
  });
  upsertSlateStatus(DATE, SLATE_ID, {
    slateLabel: "Main", status: "READY",
    poolPath: `dfs_input/${DATE}/dk_player_pool_1.json`, matchReportPath: `dfs_input/${DATE}/dk_match_report_1.json`,
    nativeSnapshotPath: `native_projection_snapshots/${DATE}/native_projection_1.json`,
  });
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-admin-publish-api-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("POST /api/admin/slates/publish", () => {
  it("401s with no session", async () => {
    const res = await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER -- publish is admin-only", async () => {
    await loginAsMember();
    const res = await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(403);
  });

  it("422s and does not publish when required readiness checks fail (e.g. no pool built yet)", async () => {
    await loginAsAdmin();
    const res = await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.readiness.ok).toBe(false);
    expect(listPublishedSlateIds(DATE)).toEqual([]);
  });

  it("publishes a ready slate: version 1, pinned paths, PUBLISHED status, audit entry, member-visible", async () => {
    const admin = await loginAsAdmin();
    makeSlateReady();

    const res = await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.dataVersion).toBe(1);

    expect(getSlateStatus(DATE, SLATE_ID)?.status).toBe("PUBLISHED");
    expect(listPublishedSlateIds(DATE)).toEqual([SLATE_ID]);
    const version = getPublishedVersion(DATE, SLATE_ID)!;
    expect(version.poolPath).toContain("dk_player_pool_1.json");
    expect(version.dataVersion).toBe(1);

    const entries = listAuditLog({ action: "slate_published" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_user_id).toBe(admin.id);
  });

  it("publishing twice increments the data version without losing history", async () => {
    await loginAsAdmin();
    makeSlateReady();
    await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    const second = await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    const body = await second.json();
    expect(body.dataVersion).toBe(2);
  });
});

describe("POST /api/admin/slates/unpublish", () => {
  it("403s for a MEMBER", async () => {
    await loginAsMember();
    const res = await unpublishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(403);
  });

  it("removes the slate from member visibility but keeps its processed artifacts", async () => {
    await loginAsAdmin();
    makeSlateReady();
    await publishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(listPublishedSlateIds(DATE)).toEqual([SLATE_ID]);

    const res = await unpublishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(200);
    expect(listPublishedSlateIds(DATE)).toEqual([]);
    expect(getPublishedVersion(DATE, SLATE_ID)).toBeNull();
    expect(getSlateStatus(DATE, SLATE_ID)?.pool_path).toContain("dk_player_pool_1.json"); // untouched
  });

  it("409s when the slate isn't currently published", async () => {
    await loginAsAdmin();
    makeSlateReady();
    const res = await unpublishSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(409);
  });
});

describe("POST /api/admin/slates/archive", () => {
  it("403s for a MEMBER", async () => {
    await loginAsMember();
    const res = await archiveSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(403);
  });

  it("archives a published slate, implicitly unpublishing it", async () => {
    await loginAsAdmin();
    makeSlateReady();
    await publishSlate(req({ date: DATE, slateId: SLATE_ID }));

    const res = await archiveSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(200);
    expect(getSlateStatus(DATE, SLATE_ID)?.status).toBe("ARCHIVED");
    expect(listPublishedSlateIds(DATE)).toEqual([]);
  });
});
