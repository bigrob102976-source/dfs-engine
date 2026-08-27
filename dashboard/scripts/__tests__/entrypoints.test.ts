import { spawn } from "node:child_process";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Milestone 33.4: regression test for a real, live-confirmed production
// blocker -- `node scripts/run-job-worker.ts` crashed on startup with
// ERR_MODULE_NOT_FOUND because this codebase's normal extensionless
// internal-import style (lib/jobs/slateJobHandlers.ts importing
// "../slatePipeline", resolved fine by Next.js's bundler and by every
// vitest-run test in this repo) is NOT resolved by Node's own native
// ESM loader. Both entry-point scripts now run via `tsx` instead of
// plain `node` (see package.json's "worker"/"db:migrate:postgres"
// scripts) -- this test spawns the REAL commands as real subprocesses,
// the only way to actually exercise Node's native module resolution;
// no bundled/transformed test runner (including vitest itself) can
// reproduce this class of bug.

const DASHBOARD_ROOT = path.resolve(__dirname, "../..");

function runCommand(command: string, args: string[], timeoutMs: number): Promise<{ stdout: string; stderr: string; timedOut: boolean; exitCode: number | null }> {
  return new Promise((resolve) => {
    // shell:true only because Windows' `npm` is a .cmd wrapper spawn()
    // can't locate directly without a shell -- every argument here is a
    // fixed literal this test file itself wrote, never external input,
    // so this doesn't carry the injection risk shell:true normally does
    // (contrast lib/orchestrator/pythonRunner.ts, which never uses it).
    const child = spawn(command, args, { cwd: DASHBOARD_ROOT, shell: true });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      resolve({ stdout, stderr, timedOut: true, exitCode: null });
    }, timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ stdout, stderr, timedOut: false, exitCode: code });
    });
  });
}

describe("standalone entry-point scripts start via their real npm commands", () => {
  it("`npm run worker` starts and begins polling, never crashing with a module-resolution error", async () => {
    // The worker runs a poll loop forever -- give it a few seconds to
    // print its startup line, then kill it. A crash (ERR_MODULE_NOT_FOUND
    // or any other startup exception) exits almost immediately instead,
    // well within this window, and is what this test is really guarding
    // against.
    const result = await runCommand("npm", ["run", "worker"], 6000);
    expect(result.stderr).not.toMatch(/ERR_MODULE_NOT_FOUND/);
    expect(result.stderr).not.toMatch(/Cannot find module/);
    expect(result.stdout).toMatch(/\[job-worker\].*starting/);
    // It should still be running (killed by our timeout), not have
    // exited on its own -- an early exit means it crashed.
    expect(result.timedOut).toBe(true);
  }, 10000);

  it("`npm run db:migrate:postgres` starts and reaches its own DATABASE_URL guard, never a module-resolution error", async () => {
    const result = await runCommand("npm", ["run", "db:migrate:postgres"], 15000);
    expect(result.stderr).not.toMatch(/ERR_MODULE_NOT_FOUND/);
    expect(result.stderr).not.toMatch(/Cannot find module/);
    expect(result.stdout + result.stderr).toMatch(/DATABASE_URL is not set/);
  }, 20000);
});
