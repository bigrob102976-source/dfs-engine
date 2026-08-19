import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const DATE = "2026-08-17";
vi.mock("@/lib/currentDate", () => ({ getTodayChicagoDate: () => DATE }));

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
const { publishSlateRecord, upsertSlateStatus } = await import("@/lib/db/slateStatus");
import SlateManagerPage from "../page";

async function stubSlates(slates: unknown[]) {
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async (script: string) => {
    if (script === "scripts/list_dfs_slates.py") {
      return {
        exitCode: 0,
        stdout: JSON.stringify({
          status: slates.length ? "ready" : "not_connected", reason: null, provider_name: "draftkings_csv",
          provider_type: "real", is_mock: false, is_connected: slates.length > 0,
          source: "real_dk_csv", slates, slates_available: slates.length,
        }),
        stderr: "",
        command: [],
      };
    }
    throw new Error(`Unexpected script call: ${script}`);
  });
}

async function loginAsMember() {
  const member = createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
  return member;
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

afterEach(async () => {
  vi.restoreAllMocks();
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

describe("SlateManagerPage (member, read-only)", () => {
  it("shows an honest empty state when no slates are published yet", async () => {
    await loginAsMember();
    await stubSlates([{ slate_id: "main", slate_name: "Main", game_count: 9, start_time: null, game_ids: ["g1"], player_count: 142 }]);
    // "main" was discovered but never published -- must not appear to a member.
    render(await SlateManagerPage());
    expect(screen.getByText(/No slates have been published yet/)).toBeInTheDocument();
  });

  it("never renders any upload/backend-refresh/remove control -- only the read-only 'Refresh status' re-render button", async () => {
    await loginAsMember();
    await stubSlates([]);
    render(await SlateManagerPage());
    expect(screen.queryByText(/Import DraftKings Slates/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Remove Local Slate/i)).not.toBeInTheDocument();
    // "Refresh Data" (admin-only, triggers the backend pipeline -- see
    // components/admin/AdminSlateOperations.tsx) must never appear here.
    expect(screen.queryByRole("button", { name: "Refresh Data" })).not.toBeInTheDocument();
    // Milestone 30.1: "Refresh status" IS expected -- it only re-renders
    // this already-published page (router.refresh()), never triggers the
    // backend pipeline. See components/RefreshStatusButton.tsx.
    expect(screen.getByRole("button", { name: "Refresh status" })).toBeInTheDocument();
  });

  it("shows a published slate's Last Updated and per-signal Data Status", async () => {
    await loginAsMember();
    await stubSlates([{ slate_id: "main", slate_name: "Main", game_count: 9, start_time: null, game_ids: ["g1"], player_count: 142 }]);
    const admin = createUser({ email: "admin@example.com", passwordHash: "h" });
    updateUserRole(admin.id, "ADMIN");
    upsertSlateStatus(DATE, "main", { slateLabel: "Main", status: "READY" });
    publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: admin.id,
      poolPath: "dfs_input/x/pool.json", matchReportPath: null, ownershipPath: "ownership_predictions/x/o.json",
      nativeSnapshotPath: "native_projection_snapshots/x/n.json", aiSnapshotPath: null,
      vegasSnapshotPath: "game_environment_snapshots/x/e.json", researchSnapshotPath: null, sourceHash: "h1",
    });

    render(await SlateManagerPage());

    expect(screen.getByText("Main")).toBeInTheDocument();
    expect(screen.getByText("Last Updated")).toBeInTheDocument();
    // Lineups (pool), Vegas, Native, Ownership are pinned -- READY. AI is not pinned -- "--".
    expect(screen.getAllByText("READY").length).toBe(4);
  });

  describe("Milestone 30.1: Player Pool eligibility widget", () => {
    let tmpDir: string;
    let originalRoot: string | undefined;

    beforeEach(() => {
      tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-member-slates-"));
      originalRoot = process.env.MLB_DFS_ROOT;
      process.env.MLB_DFS_ROOT = tmpDir;
    });

    afterEach(() => {
      if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
      else process.env.MLB_DFS_ROOT = originalRoot;
      fs.rmSync(tmpDir, { recursive: true, force: true });
    });

    it("shows Starting Pitchers/Hitters confirmed counts and Optimizer Eligible from the published match report", async () => {
      await loginAsMember();
      await stubSlates([{ slate_id: "main", slate_name: "Main", game_count: 9, start_time: null, game_ids: ["g1"], player_count: 142 }]);
      const admin = createUser({ email: "admin-widget@example.com", passwordHash: "h" });
      updateUserRole(admin.id, "ADMIN");
      upsertSlateStatus(DATE, "main", { slateLabel: "Main", status: "READY" });

      const matchReportPath = path.join(tmpDir, "dfs_input", DATE, "dk_match_report_x.json");
      fs.mkdirSync(path.dirname(matchReportPath), { recursive: true });
      fs.writeFileSync(
        matchReportPath,
        JSON.stringify({
          dk_games_total: 9,
          eligibility: { starting_pitchers: 16, confirmed_hitters: 144, waiting_for_lineups: 18, optimizer_eligible: 160 },
        }),
      );

      publishSlateRecord({
        slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: admin.id,
        poolPath: "dfs_input/x/pool.json", matchReportPath,
        ownershipPath: null, nativeSnapshotPath: null, aiSnapshotPath: null,
        vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: "h1",
      });

      render(await SlateManagerPage());

      expect(screen.getByText("Player Pool")).toBeInTheDocument();
      expect(screen.getByText("16/18 confirmed")).toBeInTheDocument(); // 9 games x 2 pitcher slots
      expect(screen.getByText("144/162 confirmed")).toBeInTheDocument(); // 9 games x 18 hitter slots
      expect(screen.getByText("18 hitters waiting for lineups to post")).toBeInTheDocument();
      expect(screen.getByText("160")).toBeInTheDocument();
    });
  });
});
