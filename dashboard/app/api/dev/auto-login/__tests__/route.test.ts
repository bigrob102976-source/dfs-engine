import { NextRequest } from "next/server";
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
const { GET } = await import("../route");

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  vi.unstubAllEnvs();
});
afterEach(() => {
  vi.unstubAllEnvs();
});

function req(url: string) {
  return new NextRequest(url);
}

describe("GET /api/dev/auto-login", () => {
  it("dev+flag=true: redirects to `next` with a real session cookie set", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

    const res = await GET(req("http://localhost:3000/api/dev/auto-login?next=%2Fdashboard%2Fnfl"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard/nfl");
    expect(cookieStore.has("bigmoney_session")).toBe(true);
  });

  it("dev+flag=false: redirects to /login, no session cookie set", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "false");

    const res = await GET(req("http://localhost:3000/api/dev/auto-login?next=%2Fdashboard%2Fnfl"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/login");
    expect(cookieStore.size).toBe(0);
  });

  it("production+flag=true: redirects to /login, no session cookie set -- production is never bypassed", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

    const res = await GET(req("http://localhost:3000/api/dev/auto-login?next=%2Fdashboard%2Fnfl"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/login");
    expect(cookieStore.size).toBe(0);
  });

  it("rejects an absolute/external `next` target (open-redirect guard)", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("LOCAL_DEV_AUTO_LOGIN", "true");

    const res = await GET(req("http://localhost:3000/api/dev/auto-login?next=https%3A%2F%2Fevil.example.com"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard/nfl");
  });
});
