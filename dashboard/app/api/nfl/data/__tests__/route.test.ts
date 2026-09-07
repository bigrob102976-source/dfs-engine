import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { __resetRateLimitForTests } = await import("@/lib/rateLimit");
const { GET } = await import("../route");

function request(url: string) {
  return new Request(url);
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

describe("GET /api/nfl/data -- NFL public access, no auth required", () => {
  it("requires no authentication at all -- an anonymous request gets real data", async () => {
    mockPythonSuccess({ draft_group_id: 151307, players: [] });
    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=151307"));
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.draft_group_id).toBe(151307);
  });

  it("400s on a missing/invalid draftGroupId", async () => {
    const res = await GET(request("http://localhost/api/nfl/data"));
    expect(res.status).toBe(400);
  });

  it("surfaces a real Python-reported error as 422, never fabricates data", async () => {
    mockPythonSuccess({ error: "DraftGroup 999 not found in current NFL universe." });
    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=999&refresh=1"));
    expect(res.status).toBe(422);
  });

  it("502s when the Python process itself fails", async () => {
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "Traceback...", command: [] });
    const res = await GET(request("http://localhost/api/nfl/data?draftGroupId=424242&refresh=1"));
    expect(res.status).toBe(502);
  });

  it("429s once the per-IP rate limit is exceeded", async () => {
    mockPythonSuccess({ draft_group_id: 777, players: [] });
    for (let i = 0; i < 20; i++) {
      const res = await GET(request(`http://localhost/api/nfl/data?draftGroupId=${700 + i}`));
      expect(res.status).toBe(200);
    }
    const blocked = await GET(request("http://localhost/api/nfl/data?draftGroupId=999999"));
    expect(blocked.status).toBe(429);
  });
});
