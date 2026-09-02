import { describe, expect, it } from "vitest";

import { parseArgs } from "../promote-canonical-slate";

describe("M4M: promote-canonical-slate.ts parseArgs (batch --key support)", () => {
  it("a single --key behaves exactly as the pre-M4 single-key invocation did", () => {
    expect(parseArgs(["--key", "normalized/MLB/x.json"])).toEqual({ keys: ["normalized/MLB/x.json"], expectedHash: undefined });
  });

  it("repeated --key flags collect into an array, in order", () => {
    expect(parseArgs(["--key", "k1", "--key", "k2", "--key", "k3"])).toEqual({ keys: ["k1", "k2", "k3"], expectedHash: undefined });
  });

  it("--expected-hash is still accepted alongside a single --key", () => {
    expect(parseArgs(["--key", "k1", "--expected-hash", "abc123"])).toEqual({ keys: ["k1"], expectedHash: "abc123" });
  });

  it("throws with a clear usage message when no --key is given", () => {
    expect(() => parseArgs([])).toThrow(/Usage/);
  });
});
