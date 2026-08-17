import { describe, expect, it } from "vitest";

import { sanitizeNextPath } from "../safeRedirect";

describe("sanitizeNextPath", () => {
  it("allows a normal internal path", () => {
    expect(sanitizeNextPath("/dashboard/optimizer")).toBe("/dashboard/optimizer");
  });

  it("falls back to /dashboard when missing", () => {
    expect(sanitizeNextPath(undefined)).toBe("/dashboard");
    expect(sanitizeNextPath(null)).toBe("/dashboard");
    expect(sanitizeNextPath("")).toBe("/dashboard");
  });

  it("blocks an absolute external URL (open redirect)", () => {
    expect(sanitizeNextPath("https://evil.example/phish")).toBe("/dashboard");
    expect(sanitizeNextPath("http://evil.example")).toBe("/dashboard");
  });

  it("blocks a protocol-relative URL (open redirect)", () => {
    expect(sanitizeNextPath("//evil.example")).toBe("/dashboard");
  });

  it("blocks the backslash variant some browsers normalize to //", () => {
    expect(sanitizeNextPath("/\\evil.example")).toBe("/dashboard");
  });

  it("blocks a bare protocol string like javascript:", () => {
    expect(sanitizeNextPath("javascript:alert(1)")).toBe("/dashboard");
  });
});
