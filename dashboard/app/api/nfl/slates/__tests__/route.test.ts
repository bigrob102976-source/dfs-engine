import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/orchestrator/pythonRunner", () => ({
  runPythonScript: vi.fn(),
  tail: (s: string) => s,
}));

const { runPythonScript } = await import("@/lib/orchestrator/pythonRunner");
const { GET } = await import("../route");

afterEach(() => {
  vi.clearAllMocks();
});

function mockPythonSuccess(payload: unknown) {
  (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    exitCode: 0, stdout: JSON.stringify(payload), stderr: "", command: [],
  });
}

describe("GET /api/nfl/slates -- NFL public access, no auth required", () => {
  it("requires no authentication at all -- an anonymous request discovers real slates", async () => {
    mockPythonSuccess({ slates: [{ draft_group_id: 151307, slate_date: "2026-09-13" }] });
    const res = await GET();
    const json = await res.json();
    expect(res.status).toBe(200);
    expect(json.slates).toHaveLength(1);
  });

  it("surfaces a real discovery failure as 502", async () => {
    (runPythonScript as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "boom", command: [] });
    const res = await GET();
    expect(res.status).toBe(502);
  });
});
