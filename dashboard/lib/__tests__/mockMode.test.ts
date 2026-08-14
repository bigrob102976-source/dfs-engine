import { afterEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../orchestrator/pythonRunner";

function ok(stdout: string): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}

type Handler = (args: string[]) => PythonRunResult;

function makeFakeRunner(handlers: Record<string, Handler>): PythonRunner {
  return async (script, args) => {
    const handler = handlers[script];
    if (!handler) throw new Error(`No fake handler registered for script: ${script}`);
    return handler(args);
  };
}

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

describe("getMockModeEnabled", () => {
  it("returns false when the script reports disabled", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner({ "scripts/get_mock_mode.py": () => ok(JSON.stringify({ enabled: false })) }));
    const { getMockModeEnabled } = await import("../mockMode");
    expect(await getMockModeEnabled()).toBe(false);
  });

  it("returns true when the script reports enabled", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner({ "scripts/get_mock_mode.py": () => ok(JSON.stringify({ enabled: true })) }));
    const { getMockModeEnabled } = await import("../mockMode");
    expect(await getMockModeEnabled()).toBe(true);
  });
});

describe("setMockModeEnabled", () => {
  it("passes --enabled true/false and returns the new state", async () => {
    const calls: string[][] = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script, args) => {
      calls.push(args);
      return ok(JSON.stringify({ status: "ok", enabled: args.includes("true") }));
    });
    const { setMockModeEnabled } = await import("../mockMode");

    const result = await setMockModeEnabled(true);
    expect(result).toEqual({ ok: true, enabled: true });
    expect(calls[0]).toEqual(["--enabled", "true"]);

    const result2 = await setMockModeEnabled(false);
    expect(result2).toEqual({ ok: true, enabled: false });
    expect(calls[1]).toEqual(["--enabled", "false"]);
  });

  it("surfaces an error when the script fails unexpectedly", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({ exitCode: 1, stdout: "", stderr: "boom", command: [] }));
    const { setMockModeEnabled } = await import("../mockMode");
    const result = await setMockModeEnabled(true);
    expect("error" in result).toBe(true);
  });
});
