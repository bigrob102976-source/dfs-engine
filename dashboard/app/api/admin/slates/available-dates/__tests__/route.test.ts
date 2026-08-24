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

const mockRunPythonScript = vi.fn();
vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: (...args: unknown[]) => mockRunPythonScript(...args),
  tail: (s: string) => s,
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getTodayChicagoDate } = await import("@/lib/currentDate");
const { GET } = await import("../route");

async function loginAsAdmin() {
  const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
}

async function loginAsMember() {
  const user = await createUser({ email: "member@example.com", passwordHash: "h" });
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockRunPythonScript.mockReset();
});

describe("GET /api/admin/slates/available-dates -- Milestone 31.2C", () => {
  it("rejects a non-admin member", async () => {
    await loginAsMember();
    const res = await GET();
    expect(res.status).toBe(403);
    expect(mockRunPythonScript).not.toHaveBeenCalled();
  });

  it("smart default is today when today already has a usable slate", async () => {
    await loginAsAdmin();
    const today = getTodayChicagoDate();
    mockRunPythonScript.mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "ok", provider_name: "draftkings_unofficial",
        dates: [{ date: today, slate_count: 12, salary_cap_slate_count: 8, has_usable_slate: true, best_slate_id: "dkunofficial-1", best_slate_label: "Featured", best_game_count: 13 }],
      }),
      stderr: "",
    });
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.smartDefaultDate).toBe(today);
  });

  it("smart default is the nearest future usable date when today has none (the exact scenario this milestone fixes)", async () => {
    await loginAsAdmin();
    const today = getTodayChicagoDate();
    // Computed relative to "today" (never hardcoded absolute dates) so
    // this test stays correct regardless of which real calendar date it
    // runs on -- a hardcoded future date eventually becomes the past.
    const offsetDate = (days: number) => {
      const d = new Date(`${today}T12:00:00Z`);
      d.setUTCDate(d.getUTCDate() + days);
      return d.toISOString().slice(0, 10);
    };
    const nearDate = offsetDate(2);
    const farDate = offsetDate(6);
    mockRunPythonScript.mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "ok", provider_name: "draftkings_unofficial",
        dates: [
          { date: farDate, slate_count: 1, salary_cap_slate_count: 1, has_usable_slate: true, best_slate_id: "dkunofficial-far", best_slate_label: "Featured", best_game_count: 12 },
          { date: nearDate, slate_count: 15, salary_cap_slate_count: 11, has_usable_slate: true, best_slate_id: "dkunofficial-152400", best_slate_label: "Featured", best_game_count: 13 },
        ],
      }),
      stderr: "",
    });
    const res = await GET();
    const body = await res.json();
    expect(body.today).toBe(today);
    // Nearest future usable date wins over a farther-out one, even
    // though the farther one appears first in the unsorted fixture.
    expect(body.smartDefaultDate).toBe(nearDate);
  });

  it("smart default falls back to today (normal empty-state) when no date has a usable slate", async () => {
    await loginAsAdmin();
    const today = getTodayChicagoDate();
    mockRunPythonScript.mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", provider_name: "draftkings_unofficial", dates: [] }),
      stderr: "",
    });
    const res = await GET();
    const body = await res.json();
    expect(body.smartDefaultDate).toBe(today);
    expect(body.dates).toEqual([]);
  });

  it("passes through not_applicable status for a non-DK-unofficial provider configuration", async () => {
    await loginAsAdmin();
    mockRunPythonScript.mockResolvedValue({
      exitCode: 0,
      stdout: JSON.stringify({ status: "not_applicable", provider_name: null, reason: "DK unofficial provider is not the active provider.", dates: [] }),
      stderr: "",
    });
    const res = await GET();
    const body = await res.json();
    expect(body.status).toBe("not_applicable");
  });

  it("reports unavailable honestly on script/parse failure, never throws", async () => {
    await loginAsAdmin();
    mockRunPythonScript.mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom" });
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("unavailable");
    expect(body.dates).toEqual([]);
  });
});
