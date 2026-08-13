import { spawn } from "node:child_process";

import { getArtifactRoot } from "../artifactRoot";

export interface PythonRunResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  command: string[];
}

export type PythonRunner = (scriptRelativePath: string, args: string[]) => Promise<PythonRunResult>;

function resolvePythonExecutable(): string {
  return process.env.MLB_DFS_PYTHON || "python";
}

/** Runs a project Python script as a subprocess: explicit executable +
 * argv array, cwd pinned to the project root, shell disabled -- never a
 * concatenated shell string, so nothing in `args` can be interpreted as
 * shell syntax regardless of its contents. Callers are responsible for
 * only passing args that came from server-trusted sources (the resolved
 * "today" date, an already-discovered slate id) -- see
 * runner.ts::resumeWithSlateSelection for where a browser-supplied value
 * is validated against a known-good allowlist before it ever reaches
 * here. */
const spawnPythonScript: PythonRunner = (scriptRelativePath, args) => {
  const projectRoot = getArtifactRoot();
  const executable = resolvePythonExecutable();
  const argv = [scriptRelativePath, ...args];

  return new Promise((resolve, reject) => {
    let child;
    try {
      // turbopackIgnore: this dashboard always runs locally (next dev / next start
      // on the user's own machine, never a serverless/edge deploy target), so the
      // build-time file-tracing this dynamic spawn() would otherwise trigger is
      // not relevant here.
      child = spawn(/*turbopackIgnore: true*/ executable, argv, { cwd: projectRoot, shell: false, windowsHide: true });
    } catch (err) {
      reject(err);
      return;
    }

    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });
    child.on("error", (err) => reject(err));
    child.on("close", (code) => {
      resolve({ exitCode: code, stdout, stderr, command: [executable, ...argv] });
    });
  });
};

// Swappable at test time (see __setPythonRunnerForTests) so orchestrator
// tests never spawn a real Python process or touch the network -- they
// inject a fake that writes fixture artifact files and returns a
// synthetic result instead.
let activeImpl: PythonRunner = spawnPythonScript;

export function runPythonScript(scriptRelativePath: string, args: string[]): Promise<PythonRunResult> {
  return activeImpl(scriptRelativePath, args);
}

export function __setPythonRunnerForTests(impl: PythonRunner): void {
  activeImpl = impl;
}

export function __resetPythonRunnerForTests(): void {
  activeImpl = spawnPythonScript;
}

export function tail(text: string, maxChars = 4000): string {
  if (text.length <= maxChars) return text;
  return `... (truncated) ...\n${text.slice(text.length - maxChars)}`;
}
