import { afterEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../orchestrator/pythonRunner";

function ok(stdout: string): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}

function argValue(args: string[], flag: string): string | undefined {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : undefined;
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

describe("uploadDraftKingsCsv", () => {
  it("writes the uploaded bytes to a temp file, calls the upload script, and cleans up", async () => {
    const fs = await import("node:fs");
    let seenCsvPath: string | undefined;
    let seenContent: string | null = null;
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({
        "scripts/upload_draftkings_csv.py": (args) => {
          seenCsvPath = argValue(args, "--csv-path");
          seenContent = fs.readFileSync(seenCsvPath!, "utf-8");
          return ok(JSON.stringify({ status: "ready", path: "x.csv", slate_label: argValue(args, "--slate-label"), player_count: 171 }));
        },
      }),
    );

    const { uploadDraftKingsCsv } = await import("../draftKingsUpload");
    const result = await uploadDraftKingsCsv(Buffer.from("Name,Salary\nAce,9000\n"), "2026-08-14", "Main", "DKSalaries.csv");

    expect(result).toEqual({ status: "ready", path: "x.csv", slate_label: "Main", player_count: 171 });
    expect(seenContent).toBe("Name,Salary\nAce,9000\n");
    expect(seenCsvPath).toBeTruthy();
    expect(fs.existsSync(seenCsvPath!)).toBe(false); // temp dir cleaned up after the call
  });

  it("surfaces a validation error from the script", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({
        "scripts/upload_draftkings_csv.py": () => ok(JSON.stringify({ status: "error", reason: "DraftKings CSV does not look like a Classic MLB salary export." })),
      }),
    );
    const { uploadDraftKingsCsv } = await import("../draftKingsUpload");
    const result = await uploadDraftKingsCsv(Buffer.from("not,a,dk,csv"), "2026-08-14", "Main", "bad.csv");
    expect(result.status).toBe("error");
  });
});

describe("listDraftKingsUploads", () => {
  it("returns the uploads array", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({
        "scripts/list_draftkings_uploads.py": () => ok(JSON.stringify({ status: "ok", uploads: [{ slate_label: "Main" }] })),
      }),
    );
    const { listDraftKingsUploads } = await import("../draftKingsUpload");
    const result = await listDraftKingsUploads("2026-08-14");
    expect(result).toEqual([{ slate_label: "Main" }]);
  });
});

describe("deleteDraftKingsUpload", () => {
  it("returns ok on success", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner({ "scripts/delete_draftkings_upload.py": () => ok(JSON.stringify({ status: "ok" })) }));
    const { deleteDraftKingsUpload } = await import("../draftKingsUpload");
    expect(await deleteDraftKingsUpload("some/path.csv")).toEqual({ ok: true });
  });

  it("surfaces an error reason", async () => {
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({ "scripts/delete_draftkings_upload.py": () => ok(JSON.stringify({ status: "error", reason: "Not an uploaded DraftKings CSV." })) }),
    );
    const { deleteDraftKingsUpload } = await import("../draftKingsUpload");
    expect(await deleteDraftKingsUpload("../etc/passwd")).toEqual({ error: "Not an uploaded DraftKings CSV." });
  });
});
