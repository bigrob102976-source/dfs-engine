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
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { __resetStorageForTests } = await import("@/lib/storage/getStorage");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getSlateStatus } = await import("@/lib/db/slateStatus");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { POST: discoverSlates } = await import("../discover/route");

let tmpDir: string;
const DATE = "2026-08-24";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function req(body: unknown) {
  return new Request("http://localhost/x", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

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

let tsCounter = 0;
function nextTs(): string {
  tsCounter += 1;
  return String(tsCounter).padStart(10, "0");
}

// Two real Classic slates -- mirrors a live DraftKings Unofficial
// provider response shape (dfs/providers/draftkings_unofficial_provider.py).
const TURBO = { slate_id: "dkunofficial-152565", slate_name: "Turbo", game_count: 3, player_count: 282 };
const FEATURED = { slate_id: "dkunofficial-152567", slate_name: "Featured", game_count: 7, player_count: 652 };

let discoveryStatus: "ready" | "not_connected" = "ready";

beforeEach(async () => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  tsCounter = 0;
  discoveryStatus = "ready";
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-admin-discover-api-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
  // Milestone 33.2.1: a native projection snapshot is written ONCE (it's
  // date-scoped, not slate-scoped -- see dashboard/lib/artifactRoot.ts's
  // ARTIFACT_DIRS comment) so readiness's native_projections check
  // passes for BOTH slates below without needing a second write.
  let nativeSnapshotWritten = false;

  function argValue(args: string[], flag: string): string | null {
    const i = args.indexOf(flag);
    return i >= 0 && i + 1 < args.length ? args[i + 1] : null;
  }

  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async (script, args) => {
    if (script === "scripts/list_dfs_slates.py") {
      if (discoveryStatus === "not_connected") {
        return {
          exitCode: 0,
          stdout: JSON.stringify({
            status: "not_connected", reason: "No live DraftKings salary provider configured.",
            provider_name: null, provider_type: null, is_mock: false, is_connected: false, source: "unconfigured",
            slates: [], slates_available: 0, warnings: [],
          }),
          stderr: "", command: [],
        };
      }
      return {
        exitCode: 0,
        stdout: JSON.stringify({
          status: "ready", reason: null, provider_name: "draftkings_unofficial", provider_type: "real",
          is_mock: false, is_connected: true, source: "explicit",
          slates: [TURBO, FEATURED], slates_available: 2, warnings: [],
        }),
        stderr: "", command: [],
      };
    }
    if (script === "scripts/fetch_dfs_slate.py") {
      const slateId = argValue(args, "--slate-id") ?? TURBO.slate_id;
      const providerSlatePath = `dfs_input/${DATE}/provider_slate_${nextTs()}.json`;
      writeJson(providerSlatePath, {
        status: "ready", provider_name: "draftkings_unofficial", is_mock: false, source: "explicit",
        selected_slate_id: slateId, slates: [TURBO, FEATURED], players: [],
      });
      return { exitCode: 0, stdout: `File written:\n  - ${path.join(tmpDir, providerSlatePath)}`, stderr: "", command: [] };
    }
    if (script === "scripts/build_dfs_pool_from_provider.py") {
      const providerSlatePath = argValue(args, "--provider-slate");
      const providerDoc = providerSlatePath ? (JSON.parse(fs.readFileSync(providerSlatePath, "utf-8")) as { selected_slate_id: string }) : null;
      const slateId = providerDoc?.selected_slate_id ?? TURBO.slate_id;
      const ts = nextTs();
      writeJson(`dfs_input/${DATE}/dk_player_pool_${ts}.json`, {
        selected_slate_id: slateId, roster_feasibility_pass: true, player_count: 1,
        players: [{ dk_player_id: "d1", mlb_player_id: "h1", name: "X", team: "AAA", player_type: "hitter",
          dk_positions: ["OF"], salary: 4000, lineup_status: "active", match_status: "matched", source_sha256: "hash1" }],
      });
      writeJson(`dfs_input/${DATE}/dk_match_report_${ts}.json`, {
        selected_slate_id: slateId, dk_entries: 1, dk_games_total: 1, dk_games_matched_to_research: 1,
        source_provenance: "DRAFTKINGS_UNOFFICIAL_LIVE", identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    }
    if (script === "scripts/project_dk_ownership.py") {
      const slateId = argValue(args, "--slate-id") ?? TURBO.slate_id;
      writeJson(`ownership_predictions/${DATE}/${slateId}/ownership_${nextTs()}.json`, {
        slate_id: slateId, players: [{ dk_player_id: "d1", mlb_player_id: "h1", projected_ownership: 20, leverage_score: 1 }],
      });
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    }
    if (script === "scripts/run_native_projection_engine.py") {
      if (!nativeSnapshotWritten) {
        nativeSnapshotWritten = true;
        writeJson(`native_projection_snapshots/${DATE}/native_projection_${nextTs()}.json`, {
          slate_date: DATE, generated_at: "2026-08-24T12:00:00Z", model_version: "1.0.0", player_count: 1,
          players: [{ player_id: "h1", name: "X", team: "AAA", player_type: "hitter" }], warnings: [],
        });
      }
      return { exitCode: 0, stdout: JSON.stringify({ status: "ready" }), stderr: "", command: [] };
    }
    return { exitCode: 0, stdout: JSON.stringify({ status: "ready" }), stderr: "", command: [] };
  });
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  const { __resetPoolCacheForTests } = await import("@/lib/optimizerWorkspace/poolCache");
  __resetPythonRunnerForTests();
  __resetPoolCacheForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("POST /api/admin/slates/discover", () => {
  it("401s with no session", async () => {
    const res = await discoverSlates(req({ date: DATE }));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    await loginAsMember();
    const res = await discoverSlates(req({ date: DATE }));
    expect(res.status).toBe(403);
  });

  it("400s on an invalid date", async () => {
    await loginAsAdmin();
    const res = await discoverSlates(req({ date: "not-a-date" }));
    expect(res.status).toBe(400);
  });

  it("discovers every real Classic slate and starts a pipeline job for each, without ever requiring a CSV", async () => {
    const admin = await loginAsAdmin();
    const res = await discoverSlates(req({ date: DATE }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.providerName).toBe("draftkings_unofficial");
    expect(body.providerStatus).toBe("ready");
    expect(body.isMock).toBe(false);
    expect(body.slatesDiscovered).toHaveLength(2);
    expect(body.slatesDiscovered.map((s: { slateId: string }) => s.slateId).sort()).toEqual([FEATURED.slate_id, TURBO.slate_id].sort());
    expect(body.jobs).toHaveLength(2);
    expect(body.jobs.every((j: { jobId: string | null; action: string }) => j.jobId !== null && j.action === "process")).toBe(true);

    expect(await listAuditLog({ action: "slate_discover_started" })).toHaveLength(1);
    expect((await listAuditLog({ action: "slate_discover_started" }))[0].actor_user_id).toBe(admin.id);

    // Let the fire-and-forget pipelines settle, then confirm both slates
    // actually progressed through the real (mocked) pipeline.
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect((await getSlateStatus(DATE, TURBO.slate_id))?.status).toBe("READY");
    expect((await getSlateStatus(DATE, FEATURED.slate_id))?.status).toBe("READY");
    expect(await listAuditLog({ action: "slate_process_started" })).toHaveLength(2);
  });

  it("never fabricates slates when the provider isn't connected -- surfaces the real reason instead", async () => {
    discoveryStatus = "not_connected";
    await loginAsAdmin();
    const res = await discoverSlates(req({ date: DATE }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.providerStatus).toBe("not_connected");
    expect(body.providerReason).toBe("No live DraftKings salary provider configured.");
    expect(body.slatesDiscovered).toHaveLength(0);
    expect(body.jobs).toHaveLength(0);
  });

  it("re-discovering an already-processed slate refreshes it instead of re-processing", async () => {
    await loginAsAdmin();
    await discoverSlates(req({ date: DATE }));
    await new Promise((resolve) => setTimeout(resolve, 500));

    const res = await discoverSlates(req({ date: DATE }));
    const body = await res.json();
    expect(body.jobs.every((j: { action: string }) => j.action === "refresh")).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(await listAuditLog({ action: "slate_refresh_started" })).toHaveLength(2);
  });
});
