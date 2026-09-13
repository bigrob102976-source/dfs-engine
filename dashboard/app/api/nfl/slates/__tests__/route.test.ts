import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { __resetRateLimitForTests } = await import("@/lib/rateLimit");
const { GET } = await import("../route");

function request() {
  return new Request("http://localhost/api/nfl/slates");
}

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

beforeEach(() => {
  __resetRateLimitForTests();
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/nfl/slates -- PUBLIC READ, no auth required", () => {
  it("requires no authentication at all -- an anonymous request discovers real slates", async () => {
    mockPythonSuccess({ slates: [{ draft_group_id: 151307, slate_date: "2026-09-13" }] });
    const res = await GET(request());
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.slates).toHaveLength(1);
  });

  it("surfaces a real discovery failure as 502", async () => {
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });
    const res = await GET(request());
    expect(res.status).toBe(502);
  });

  // Sprint 1 (2026-09-13): this route had NO rate limit at all before --
  // proves it now bounds an anonymous flood rather than merely importing
  // the helper.
  it("rate-limits repeated anonymous requests from the same IP", async () => {
    mockPythonSuccess({ slates: [] });
    let lastStatus = 200;
    for (let i = 0; i < 40; i++) {
      const res = await GET(request());
      lastStatus = res.status;
      if (lastStatus === 429) break;
    }
    expect(lastStatus).toBe(429);
  });
});
