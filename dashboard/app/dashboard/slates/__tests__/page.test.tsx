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

  it("never renders any upload/refresh/remove control", async () => {
    await loginAsMember();
    await stubSlates([]);
    render(await SlateManagerPage());
    expect(screen.queryByText(/Import DraftKings Slates/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Remove Local Slate/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /refresh/i })).not.toBeInTheDocument();
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
});
