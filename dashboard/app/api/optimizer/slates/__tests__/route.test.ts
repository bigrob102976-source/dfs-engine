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

const mockListSlates = vi.fn();
vi.mock("@/lib/optimizerWorkspace/poolCache", () => ({
  listSlates: (...args: unknown[]) => mockListSlates(...args),
}));

const mockFilterSlates = vi.fn();
vi.mock("@/lib/memberSlateVisibility", () => ({
  filterSlatesForCurrentViewer: (...args: unknown[]) => mockFilterSlates(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getTodayChicagoDate } = await import("@/lib/currentDate");
const { GET } = await import("../route");

function req(query = "") {
  return new Request(`http://localhost/api/optimizer/slates${query}`);
}

async function loginAsMember() {
  const user = await createUser({ email: "member@example.com", passwordHash: "h" });
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockListSlates.mockReset();
  mockFilterSlates.mockReset();
  mockListSlates.mockResolvedValue({ status: "ready", slates: [], providerName: "draftkings_unofficial", isMock: false });
  mockFilterSlates.mockImplementation(async (slates: unknown[]) => slates);
});

describe("GET /api/optimizer/slates -- Milestone 31.2C date handling", () => {
  it("omitted ?date= falls back to today's America/Chicago date", async () => {
    await loginAsMember();
    const res = await GET(req());
    expect(res.status).toBe(200);
    expect(mockListSlates).toHaveBeenCalledWith(getTodayChicagoDate());
    const body = await res.json();
    expect(body.date).toBe(getTodayChicagoDate());
  });

  it("an explicit valid ?date= is used as-is", async () => {
    await loginAsMember();
    const res = await GET(req("?date=2026-08-21"));
    expect(res.status).toBe(200);
    expect(mockListSlates).toHaveBeenCalledWith("2026-08-21");
    const body = await res.json();
    expect(body.date).toBe("2026-08-21");
  });

  it("rejects a malformed ?date= with 400", async () => {
    await loginAsMember();
    const res = await GET(req("?date=nope"));
    expect(res.status).toBe(400);
    expect(mockListSlates).not.toHaveBeenCalled();
  });
});
