import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/guards", () => ({
  requireAdminApi: vi.fn(),
}));

const { requireAdminApi } = await import("@/lib/auth/guards");
const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createSavedLineup } = await import("@/lib/db/nflSavedLineups");
const { GET, DELETE } = await import("../route");

const USER = { id: "user-1", email: "admin@example.com", role: "ADMIN" };

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  (requireAdminApi as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(USER);
});

describe("GET/DELETE /api/nfl/lineups/[id]", () => {
  it("GET 404s for an unknown id", async () => {
    const res = await GET(new Request("http://localhost"), ctx("nope"));
    expect(res.status).toBe(404);
  });

  it("GET returns the real saved lineup for its owner", async () => {
    const row = await createSavedLineup({
      userId: USER.id, draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection",
      stackConfigJson: "{}", slotsJson: JSON.stringify([{ roster_slot: "QB" }]),
    });
    const res = await GET(new Request("http://localhost"), ctx(row.id));
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.id).toBe(row.id);
  });

  it("GET 404s for another user's lineup -- never leaks", async () => {
    const row = await createSavedLineup({
      userId: "someone-else", draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection",
      stackConfigJson: "{}", slotsJson: "[]",
    });
    const res = await GET(new Request("http://localhost"), ctx(row.id));
    expect(res.status).toBe(404);
  });

  it("DELETE removes the owner's lineup", async () => {
    const row = await createSavedLineup({
      userId: USER.id, draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection",
      stackConfigJson: "{}", slotsJson: "[]",
    });
    const res = await DELETE(new Request("http://localhost"), ctx(row.id));
    expect(res.status).toBe(200);
    const getRes = await GET(new Request("http://localhost"), ctx(row.id));
    expect(getRes.status).toBe(404);
  });

  it("DELETE 404s for another user's lineup, never deletes it", async () => {
    const row = await createSavedLineup({
      userId: "someone-else", draftGroupId: 151307, slateDate: "2026-09-13", mode: "projection",
      stackConfigJson: "{}", slotsJson: "[]",
    });
    const res = await DELETE(new Request("http://localhost"), ctx(row.id));
    expect(res.status).toBe(404);
  });
});
