import { beforeEach, describe, expect, it } from "vitest";

import { __resetRateLimitForTests, checkRateLimit, getClientIp } from "../rateLimit";

beforeEach(() => {
  __resetRateLimitForTests();
});

describe("checkRateLimit", () => {
  it("allows requests up to the max within the window", () => {
    for (let i = 0; i < 5; i++) {
      expect(checkRateLimit("key-a", 5, 60_000, 1000)).toBe(true);
    }
  });

  it("blocks the request once the max is exceeded within the window", () => {
    for (let i = 0; i < 5; i++) checkRateLimit("key-b", 5, 60_000, 1000);
    expect(checkRateLimit("key-b", 5, 60_000, 1000)).toBe(false);
  });

  it("allows again once the window has passed", () => {
    for (let i = 0; i < 5; i++) checkRateLimit("key-c", 5, 60_000, 1000);
    expect(checkRateLimit("key-c", 5, 60_000, 1000)).toBe(false);
    expect(checkRateLimit("key-c", 5, 60_000, 1000 + 60_001)).toBe(true);
  });

  it("tracks separate keys independently", () => {
    for (let i = 0; i < 5; i++) checkRateLimit("key-d", 5, 60_000, 1000);
    expect(checkRateLimit("key-d", 5, 60_000, 1000)).toBe(false);
    expect(checkRateLimit("key-e", 5, 60_000, 1000)).toBe(true);
  });
});

describe("getClientIp", () => {
  it("uses the first entry of x-forwarded-for", () => {
    const req = new Request("http://localhost", { headers: { "x-forwarded-for": "1.2.3.4, 5.6.7.8" } });
    expect(getClientIp(req)).toBe("1.2.3.4");
  });

  it("falls back to x-real-ip when x-forwarded-for is absent", () => {
    const req = new Request("http://localhost", { headers: { "x-real-ip": "9.9.9.9" } });
    expect(getClientIp(req)).toBe("9.9.9.9");
  });

  it("falls back to a fixed key when neither header is present, never throws", () => {
    const req = new Request("http://localhost");
    expect(getClientIp(req)).toBe("unknown");
  });
});
