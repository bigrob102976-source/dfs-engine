import { describe, expect, it } from "vitest";

import { GET } from "../route";

describe("GET /api/health", () => {
  it("returns status/version/timestamp only, unauthenticated, and nothing infrastructure-shaped", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(typeof body.version).toBe("string");
    expect(typeof body.timestamp).toBe("string");
    expect(Number.isNaN(new Date(body.timestamp).getTime())).toBe(false);
    expect(Object.keys(body).sort()).toEqual(["status", "timestamp", "version"]);
  });
});
