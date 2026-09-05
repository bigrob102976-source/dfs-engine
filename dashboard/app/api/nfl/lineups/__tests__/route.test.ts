import { NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAdminApi: vi.fn(),
}));

const { requireAdminApi } = await import("@/lib/auth/guards");
const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { GET, POST } = await import("../route");

const DG_ID = 151307;
const USER = { id: "user-1", email: "admin@example.com", role: "ADMIN" };

function slots() {
  return Array.from({ length: 9 }, (_, i) => ({ roster_slot: `S${i}`, draftkings_player_id: String(i) }));
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(USER);
});
afterEach(() => {
  vi.clearAllMocks();
});

function req(url: string, init?: RequestInit) {
  return new Request(url, init);
}

describe("GET/POST /api/nfl/lineups", () => {
  it("returns 403 for a non-admin, never touches the DB", async () => {
    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(NextResponse.json({ error: "no" }, { status: 403 }));
    const res = await GET(req(`http://localhost/api/nfl/lineups?draftGroupId=${DG_ID}`));
    expect(res.status).toBe(403);
  });

  it("400s on a missing draftGroupId", async () => {
    const res = await GET(req("http://localhost/api/nfl/lineups"));
    expect(res.status).toBe(400);
  });

  it("GET returns an empty list when nothing saved yet", async () => {
    const res = await GET(req(`http://localhost/api/nfl/lineups?draftGroupId=${DG_ID}`));
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.lineups).toEqual([]);
  });

  it("POST creates a real saved lineup, then GET returns it", async () => {
    const createRes = await POST(req("http://localhost/api/nfl/lineups", {
      method: "POST",
      body: JSON.stringify({ draftGroupId: DG_ID, slateDate: "2026-09-13", mode: "projection", stackConfig: { qbStackMode: "single" }, slots: slots() }),
    }));
    expect(createRes.status).toBe(200);
    const created = await createRes.json();
    expect(created.draft_group_id).toBe(DG_ID);
    expect(created.slots).toHaveLength(9);

    const listRes = await GET(req(`http://localhost/api/nfl/lineups?draftGroupId=${DG_ID}`));
    const list = await listRes.json();
    expect(list.lineups).toHaveLength(1);
    expect(list.lineups[0].id).toBe(created.id);
  });

  it("POST 400s when slots isn't exactly 9 entries", async () => {
    const res = await POST(req("http://localhost/api/nfl/lineups", {
      method: "POST",
      body: JSON.stringify({ draftGroupId: DG_ID, slateDate: "2026-09-13", slots: slots().slice(0, 5) }),
    }));
    expect(res.status).toBe(400);
  });

  it("lineups are scoped to the requesting user -- never leak another user's saved lineups", async () => {
    await POST(req("http://localhost/api/nfl/lineups", {
      method: "POST",
      body: JSON.stringify({ draftGroupId: DG_ID, slateDate: "2026-09-13", slots: slots() }),
    }));

    (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ ...USER, id: "user-2" });
    const res = await GET(req(`http://localhost/api/nfl/lineups?draftGroupId=${DG_ID}`));
    const json = await res.json();
    expect(json.lineups).toEqual([]);
  });
});
