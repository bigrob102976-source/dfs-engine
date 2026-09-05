import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlayerRow } from "@/lib/types";

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

vi.mock("@/lib/loaders", () => ({
  loadLatestPitcherSnapshot: vi.fn().mockResolvedValue({ data: { pitchers: [] } }),
  loadLatestBatterSnapshot: vi.fn().mockResolvedValue({ data: { hitters: [] } }),
  loadLatestOwnershipSnapshot: vi.fn().mockResolvedValue({ data: null }),
  loadLatestDKPlayerPool: vi.fn().mockResolvedValue({ data: null }),
}));

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1", playerType: "hitter", name: "Player", team: "PHI", opponent: "STL", gameId: "g1",
    position: "OF", positions: ["OF"], battingOrder: 1, salary: 4000, projection: 8.0, ceiling: 15.0, floor: 4.0,
    overall: 60.0, power: 55.0, matchup: 50.0, risk: 30.0, confidence: 90.0, ownership: 20.0, ownershipTier: "medium",
    chalkScore: 50.0, leverage: 5.0, tags: [], reasons: [],
    lineupStatus: "active", matchStatus: "matched", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true,
    mlProjection: null, mlProjectionStatus: null, blueCollarProjection: null, blueCollarMatchStatus: null,
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

const mockBuildPitcherRows = vi.fn();
const mockBuildHitterRows = vi.fn();
vi.mock("@/lib/normalize", () => ({
  buildPitcherRows: (...args: unknown[]) => mockBuildPitcherRows(...args),
  buildHitterRows: (...args: unknown[]) => mockBuildHitterRows(...args),
}));

const mockResolveSlateContext = vi.fn();
vi.mock("@/lib/slateContext", async () => {
  const actual = await vi.importActual<typeof import("@/lib/slateContext")>("@/lib/slateContext");
  return { ...actual, resolveSlateContext: (...args: unknown[]) => mockResolveSlateContext(...args) };
});

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET } = await import("../route");

async function loginAsMember() {
  const user = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockBuildPitcherRows.mockReset();
  mockBuildHitterRows.mockReset();
  mockResolveSlateContext.mockReset();
  mockResolveSlateContext.mockResolvedValue({ slates: [], selected: null, status: "ready", isMock: false, providerName: null, gameIdsUnavailable: false });
});

describe("GET /api/optimizer/insights", () => {
  it("rejects an unauthenticated request with 401", async () => {
    const res = await GET(new Request("http://localhost/api/optimizer/insights?date=2026-08-22"));
    expect(res.status).toBe(401);
  });

  it("rejects a malformed date with 400", async () => {
    await loginAsMember();
    const res = await GET(new Request("http://localhost/api/optimizer/insights?date=not-a-date"));
    expect(res.status).toBe(400);
  });

  it("returns the best value pitcher, top stacks, and best value stack, labeled with the real source", async () => {
    await loginAsMember();
    mockBuildPitcherRows.mockReturnValue([
      row({ id: "p1", playerType: "pitcher", name: "Cheap Ace", salary: 6000, projection: 24, optimizerEligible: true }),
      row({ id: "p2", playerType: "pitcher", name: "Bench Arm", salary: 4000, projection: 40, optimizerEligible: false }),
    ]);
    mockBuildHitterRows.mockReturnValue([
      row({ id: "h1", team: "PHI", name: "H1", salary: 4000, projection: 10, ceiling: 18, optimizerEligible: true }),
      row({ id: "h2", team: "PHI", name: "H2", salary: 3800, projection: 9, ceiling: 16, optimizerEligible: true }),
    ]);

    const res = await GET(new Request("http://localhost/api/optimizer/insights?date=2026-08-22&slate=dkunofficial-152543"));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.source).toBe("legacy");
    expect(typeof body.generatedAt).toBe("string");
    expect(body.bestValuePitcher.name).toBe("Cheap Ace"); // higher value than the bench (ineligible) arm despite lower raw projection
    expect(body.topStacks).toHaveLength(1);
    expect(body.topStacks[0].team).toBe("PHI");
    expect(body.bestValueStack.team).toBe("PHI");
  });

  it("echoes the resolved slateId -- insights are always scoped to the currently selected slate (Phase 11)", async () => {
    await loginAsMember();
    mockResolveSlateContext.mockResolvedValue({
      slates: [{ slateId: "dkunofficial-152543", slateName: "Featured", gameIds: ["g1"] }],
      selected: { slateId: "dkunofficial-152543", slateName: "Featured", gameIds: ["g1"] },
      status: "ready", isMock: false, providerName: "draftkings_unofficial", gameIdsUnavailable: false,
    });
    mockBuildPitcherRows.mockReturnValue([]);
    mockBuildHitterRows.mockReturnValue([]);

    const res = await GET(new Request("http://localhost/api/optimizer/insights?date=2026-08-22&slate=dkunofficial-152543"));
    const body = await res.json();
    expect(body.slateId).toBe("dkunofficial-152543");
  });

  it("returns null insights (never fabricated) when there's no eligible data yet", async () => {
    await loginAsMember();
    mockBuildPitcherRows.mockReturnValue([]);
    mockBuildHitterRows.mockReturnValue([]);

    const res = await GET(new Request("http://localhost/api/optimizer/insights?date=2026-08-22"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.bestValuePitcher).toBeNull();
    expect(body.topStacks).toEqual([]);
    expect(body.bestValueStack).toBeNull();
  });
});
