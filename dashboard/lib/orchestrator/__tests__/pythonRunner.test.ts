import { EventEmitter } from "node:events";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const spawnMock = vi.fn();
vi.mock("node:child_process", () => {
  const mocked = { spawn: (...args: unknown[]) => spawnMock(...args) };
  return { ...mocked, default: mocked };
});

function makeFakeChild() {
  const child = new EventEmitter() as EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  return child;
}

beforeEach(() => {
  spawnMock.mockReset();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  delete process.env.MLB_DFS_PYTHON;
});

describe("runPythonScript", () => {
  it("spawns an explicit executable + argv array with shell disabled and cwd pinned to the project root -- never a concatenated shell string", async () => {
    process.env.MLB_DFS_ROOT = path.join("C:", "fake-project-root");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const { runPythonScript } = await import("../pythonRunner");
    const resultPromise = runPythonScript("scripts/foo.py", ["--date", "2026-08-12", "--slate-id", "mock-main"]);

    child.stdout.emit("data", Buffer.from("hello "));
    child.stdout.emit("data", Buffer.from("world"));
    child.stderr.emit("data", Buffer.from("a warning"));
    child.emit("close", 0);

    const result = await resultPromise;
    expect(result.exitCode).toBe(0);
    expect(result.stdout).toBe("hello world");
    expect(result.stderr).toBe("a warning");

    expect(spawnMock).toHaveBeenCalledTimes(1);
    const [command, argv, options] = spawnMock.mock.calls[0];
    expect(command).toBe("python");
    // Every argument is its own array element -- nothing here is a single
    // interpolated shell string, so special characters in any arg (e.g. a
    // slate id) can never be interpreted as shell syntax.
    expect(argv).toEqual(["scripts/foo.py", "--date", "2026-08-12", "--slate-id", "mock-main"]);
    expect(options.shell).toBe(false);
    expect(path.resolve(options.cwd)).toBe(path.resolve(process.env.MLB_DFS_ROOT));
  });

  it("honors MLB_DFS_PYTHON to select a non-default python executable", async () => {
    process.env.MLB_DFS_ROOT = path.join("C:", "fake-project-root");
    process.env.MLB_DFS_PYTHON = "python3.11";
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const { runPythonScript } = await import("../pythonRunner");
    const resultPromise = runPythonScript("scripts/foo.py", []);
    child.emit("close", 0);
    await resultPromise;

    expect(spawnMock.mock.calls[0][0]).toBe("python3.11");
  });

  it("reports a non-zero exit code without throwing", async () => {
    process.env.MLB_DFS_ROOT = path.join("C:", "fake-project-root");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const { runPythonScript } = await import("../pythonRunner");
    const resultPromise = runPythonScript("scripts/foo.py", []);
    child.stderr.emit("data", Buffer.from("traceback..."));
    child.emit("close", 1);

    const result = await resultPromise;
    expect(result.exitCode).toBe(1);
    expect(result.stderr).toContain("traceback");
  });
});

describe("test-only python runner override seam", () => {
  it("__setPythonRunnerForTests replaces the implementation, __resetPythonRunnerForTests restores spawning", async () => {
    process.env.MLB_DFS_ROOT = path.join("C:", "fake-project-root");
    const { runPythonScript, __setPythonRunnerForTests, __resetPythonRunnerForTests } = await import("../pythonRunner");

    const fake = vi.fn().mockResolvedValue({ exitCode: 0, stdout: "fake", stderr: "", command: [] });
    __setPythonRunnerForTests(fake);

    const result = await runPythonScript("scripts/foo.py", ["--date", "2026-08-12"]);
    expect(result.stdout).toBe("fake");
    expect(fake).toHaveBeenCalledWith("scripts/foo.py", ["--date", "2026-08-12"]);
    expect(spawnMock).not.toHaveBeenCalled();

    __resetPythonRunnerForTests();
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);
    const resultPromise = runPythonScript("scripts/foo.py", []);
    child.emit("close", 0);
    await resultPromise;
    expect(spawnMock).toHaveBeenCalledTimes(1);
  });
});
