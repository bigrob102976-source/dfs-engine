import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { log, logger, redactFields } from "../logger";

describe("redactFields", () => {
  it("masks any key that looks like a secret, regardless of case", () => {
    const redacted = redactFields({
      password: "hunter2",
      apiKey: "sk_live_abc",
      API_KEY: "sk_live_abc",
      Authorization: "Bearer xyz",
      sessionCookie: "abc",
      stripeSecret: "sk_test_x",
      requestId: "req-1",
      status: "ok",
    });
    expect(redacted.password).toBe("[REDACTED]");
    expect(redacted.apiKey).toBe("[REDACTED]");
    expect(redacted.API_KEY).toBe("[REDACTED]");
    expect(redacted.Authorization).toBe("[REDACTED]");
    expect(redacted.sessionCookie).toBe("[REDACTED]");
    expect(redacted.stripeSecret).toBe("[REDACTED]");
    expect(redacted.requestId).toBe("req-1");
    expect(redacted.status).toBe("ok");
  });
});

describe("log", () => {
  let logSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    logSpy.mockRestore();
    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("writes a single JSON line with timestamp/level/message/fields", () => {
    const entry = log("info", "job succeeded", { jobId: "j1", durationMs: 42, status: "SUCCEEDED" });
    expect(logSpy).toHaveBeenCalledTimes(1);
    const printed = JSON.parse(logSpy.mock.calls[0][0] as string);
    expect(printed).toEqual(entry);
    expect(printed.level).toBe("info");
    expect(printed.message).toBe("job succeeded");
    expect(printed.jobId).toBe("j1");
    expect(printed.durationMs).toBe(42);
    expect(typeof printed.timestamp).toBe("string");
  });

  it("routes error level to console.error and warn to console.warn", () => {
    log("error", "boom");
    log("warn", "careful");
    expect(errorSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(logSpy).not.toHaveBeenCalled();
  });

  it("never leaks a secret-shaped field into the printed line", () => {
    log("info", "login", { password: "hunter2", token: "abc123" });
    const printed = logSpy.mock.calls[0][0] as string;
    expect(printed).not.toContain("hunter2");
    expect(printed).not.toContain("abc123");
  });

  it("logger.* convenience methods delegate to the right level", () => {
    logger.info("a");
    logger.warn("b");
    logger.error("c");
    logger.debug("d");
    expect(logSpy).toHaveBeenCalledTimes(2); // info + debug
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledTimes(1);
  });
});
