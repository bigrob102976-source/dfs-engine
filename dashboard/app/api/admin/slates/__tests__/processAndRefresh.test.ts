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
const { getSlateStatus } = await import("@/lib/db/slateStatus");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { POST: processSlate } = await import("../process/route");
const { POST: refreshSlate } = await import("../refresh/route");

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

let tsCounter = 0;
function nextTs(): string {
  tsCounter += 1;
  return String(tsCounter).padStart(10, "0");
}

beforeEach(async () => {
  __resetDbForTests();
  cookieStore.clear();
  tsCounter = 0;
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-admin-process-api-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async (script) => {
    await new Promise((resolve) => setTimeout(resolve, 15)); // simulate real subprocess latency
    if (script === "scripts/fetch_dfs_slate.py") {
      writeJson(`dfs_input/${DATE}/provider_slate_${nextTs()}.json`, {
        status: "ready", provider_name: "draftkings_csv", is_mock: false, source: "real_dk_csv",
        selected_slate_id: SLATE_ID, slates: [{ slate_id: SLATE_ID, slate_name: "Main", game_count: 1 }], players: [],
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    }
    if (script === "scripts/build_dfs_pool_from_provider.py") {
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
        selected_slate_id: SLATE_ID, roster_feasibility_pass: true, player_count: 1,
        players: [{ dk_player_id: "d1", mlb_player_id: "h1", name: "X", team: "AAA", player_type: "hitter",
          dk_positions: ["OF"], salary: 4000, lineup_status: "active", match_status: "matched", source_sha256: "hash1" }],
      });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
        dk_entries: 1, dk_games_total: 1, dk_games_matched_to_research: 1, source_provenance: "OFFICIAL_USER_UPLOAD",
        identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    }
    if (script === "scripts/project_dk_ownership.py") {
      writeJson(`ownership_predictions/${DATE}/${SLATE_ID}/ownership_${nextTs()}.json`, {
        slate_id: SLATE_ID, players: [{ dk_player_id: "d1", mlb_player_id: "h1", projected_ownership: 20, leverage_score: 1 }],
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    }
    if (script === "scripts/run_native_projection_engine.py") {
      writeJson(`native_projection_snapshots/${DATE}/native_projection_${nextTs()}.json`, {
        slate_date: DATE, generated_at: "x", model_version: "1.0.0", player_count: 1,
        players: [{ player_id: "h1", name: "X", team: "AAA", player_type: "hitter" }], warnings: [],
      });
      return { exitCode: 0, stdout: JSON.stringify({ status: "ready" }), stderr: "", command: [] };
    }
    if (script === "scripts/run_ai_projection_engine.py") {
      writeJson(`ai_projection_snapshots/${DATE}/ai_projection_${nextTs()}.json`, {
        slate_date: DATE, generated_at: "x", model_version: "0.1.0", player_count: 1,
        players: [{ player_id: "h1", name: "X" }], warnings: [],
      });
      return { exitCode: 0, stdout: JSON.stringify({ status: "ready" }), stderr: "", command: [] };
    }
    return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
  });
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("@/lib/optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("POST /api/admin/slates/process", () => {
  it("401s with no session", async () => {
    const res = await processSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER -- admin processing is admin-only", async () => {
    await loginAsMember();
    const res = await processSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(403);
  });

  it("400s on a missing slateId", async () => {
    await loginAsAdmin();
    const res = await processSlate(req({ date: DATE }));
    expect(res.status).toBe(400);
  });

  it("starts processing, records an audit entry, and eventually reaches READY", async () => {
    const admin = await loginAsAdmin();
    const res = await processSlate(req({ date: DATE, slateId: SLATE_ID, slateLabel: "Main" }));
    expect(res.status).toBe(202);

    expect(getSlateStatus(DATE, SLATE_ID)?.status).toBe("PROCESSING");
    expect(listAuditLog({ action: "slate_process_started" })).toHaveLength(1);
    expect(listAuditLog({ action: "slate_process_started" })[0].actor_user_id).toBe(admin.id);

    // Let the fire-and-forget pipeline promise settle.
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(getSlateStatus(DATE, SLATE_ID)?.status).toBe("READY");
    expect(listAuditLog({ action: "slate_process_completed" })).toHaveLength(1);
  });

  it("409s when the slate is already processing", async () => {
    await loginAsAdmin();
    await processSlate(req({ date: DATE, slateId: SLATE_ID }));
    const res = await processSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(409);
    // Let the first call's background pipeline settle before the DB resets
    // for the next test (its own fire-and-forget audit-log write would
    // otherwise race a subsequent test's __resetDbForTests()).
    await new Promise((resolve) => setTimeout(resolve, 200));
  });
});

describe("POST /api/admin/slates/refresh", () => {
  it("403s for a MEMBER", async () => {
    await loginAsMember();
    const res = await refreshSlate(req({ date: DATE, slateId: SLATE_ID }));
    expect(res.status).toBe(403);
  });

  it("re-runs the pipeline WITHOUT requiring a new upload -- same underlying data source", async () => {
    await loginAsAdmin();
    const res = await refreshSlate(req({ date: DATE, slateId: SLATE_ID, slateLabel: "Main" }));
    expect(res.status).toBe(202);
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(getSlateStatus(DATE, SLATE_ID)?.status).toBe("READY");
    expect(listAuditLog({ action: "slate_refresh_started" })).toHaveLength(1);
  });
});
