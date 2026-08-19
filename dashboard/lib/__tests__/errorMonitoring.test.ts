import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { captureError } from "../errorMonitoring";

describe("captureError", () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it("logs a structured error line with the Error's message and stack", () => {
    captureError(new Error("boom"), { jobId: "j1" });
    expect(errorSpy).toHaveBeenCalledTimes(1);
    const printed = JSON.parse(errorSpy.mock.calls[0][0] as string);
    expect(printed.level).toBe("error");
    expect(printed.message).toBe("boom");
    expect(printed.jobId).toBe("j1");
    expect(typeof printed.stack).toBe("string");
  });

  it("handles a non-Error thrown value without crashing", () => {
    captureError("plain string failure");
    const printed = JSON.parse(errorSpy.mock.calls[0][0] as string);
    expect(printed.message).toBe("plain string failure");
    expect(printed.stack).toBeUndefined();
  });
});
