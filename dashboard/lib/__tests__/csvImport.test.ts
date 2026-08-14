import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { PythonRunner, PythonRunResult } from "../orchestrator/pythonRunner";

let tmpDir: string;
const DATE = "2026-08-13";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function ok(stdout: string): PythonRunResult {
  return { exitCode: 0, stdout, stderr: "", command: [] };
}

type Handler = (args: string[]) => PythonRunResult | Promise<PythonRunResult>;

function argValue(args: string[], flag: string): string | undefined {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : undefined;
}

function makeFakeRunner(handlers: Record<string, Handler>, calls: Array<{ script: string; args: string[] }>): PythonRunner {
  return async (script, args) => {
    calls.push({ script, args });
    const handler = handlers[script];
    if (!handler) throw new Error(`No fake handler registered for script: ${script}`);
    return handler(args);
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-csvimport-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("analyzeProjectionCsv", () => {
  it("writes the uploaded bytes to a temp file, calls analyze_projection_csv.py, and cleans up", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    let seenCsvContent: string | null = null;
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/analyze_projection_csv.py": (args) => {
            const csvPath = argValue(args, "--csv-path")!;
            seenCsvContent = fs.readFileSync(csvPath, "utf-8");
            return ok(JSON.stringify({ status: "ok", headers: ["Name", "Proj"], detected_mapping: { name: "Name", projection: "Proj" }, resolved_mapping: { name: "Name", projection: "Proj" }, preview_rows: [], parse_warnings: [], validation: { players_imported: 1, matched: 0, unmatched: 0, ambiguous: 0, duplicate_players: 0, missing_salary: 0, missing_projection: 0, missing_position: 0, unknown_teams: [], unknown_opponents: [], needs_review: [] }, importable_player_count: 1, skipped_missing_name: 0, skipped_missing_projection: 0 }));
          },
        },
        calls,
      ),
    );

    const { analyzeProjectionCsv } = await import("../csvImport");
    const result = await analyzeProjectionCsv(Buffer.from("Name,Proj\nAce,10\n"), "bluecollar", DATE);

    expect("error" in result).toBe(false);
    expect(seenCsvContent).toBe("Name,Proj\nAce,10\n");
    const call = calls.find((c) => c.script === "scripts/analyze_projection_csv.py")!;
    expect(argValue(call.args, "--provider")).toBe("bluecollar");
    expect(argValue(call.args, "--date")).toBe(DATE);
    const csvPath = argValue(call.args, "--csv-path")!;
    expect(fs.existsSync(csvPath)).toBe(false); // temp dir cleaned up after the call
  });

  it("passes --mapping only when a manual mapping override is given", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        { "scripts/analyze_projection_csv.py": () => ok(JSON.stringify({ status: "ok", headers: [], detected_mapping: {}, resolved_mapping: {}, preview_rows: [], parse_warnings: [], validation: { players_imported: 0, matched: 0, unmatched: 0, ambiguous: 0, duplicate_players: 0, missing_salary: 0, missing_projection: 0, missing_position: 0, unknown_teams: [], unknown_opponents: [], needs_review: [] }, importable_player_count: 0, skipped_missing_name: 0, skipped_missing_projection: 0 })) },
        calls,
      ),
    );

    const { analyzeProjectionCsv } = await import("../csvImport");
    await analyzeProjectionCsv(Buffer.from("a,b\n1,2\n"), "bluecollar", DATE);
    expect(calls[0].args).not.toContain("--mapping");

    await analyzeProjectionCsv(Buffer.from("a,b\n1,2\n"), "bluecollar", DATE, { projection: "b" });
    expect(argValue(calls[1].args, "--mapping")).toBe(JSON.stringify({ projection: "b" }));
  });

  it("surfaces a CsvParseError-style {status: error} response as {error}", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({ "scripts/analyze_projection_csv.py": () => ok(JSON.stringify({ status: "error", reason: "Could not decode the uploaded file." })) }, calls),
    );

    const { analyzeProjectionCsv } = await import("../csvImport");
    const result = await analyzeProjectionCsv(Buffer.from([0xff, 0xfe]), "bluecollar", DATE);
    expect(result).toEqual({ error: "Could not decode the uploaded file." });
  });
});

describe("saveProjectionCsvImport", () => {
  it("saves the baseline then runs the adjustment layer against it, mirroring the provider-fetched flow", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/save_projection_csv_import.py": () =>
            ok(JSON.stringify({ status: "ready", path: "external_projection_snapshots/2026-08-13/provider_bluecollar_20260813T180000.json", player_count: 171, provider_name: "BlueCollar DFS", validation_summary: { matched: 171 } })),
          "scripts/run_projection_adjustment.py": () => ok(JSON.stringify({ status: "ready", path: "adjusted_projection_snapshots/2026-08-13/adjusted_20260813T180100.json", record_count: 171 })),
        },
        calls,
      ),
    );

    const { saveProjectionCsvImport } = await import("../csvImport");
    const result = await saveProjectionCsvImport(Buffer.from("Name,Proj\nAce,10\n"), "bluecollar", DATE, "bluecollar.csv");

    expect(result.status).toBe("ready");
    expect(result.player_count).toBe(171);
    expect(result.adjustment).toEqual({ status: "ready", record_count: 171, reason: undefined });
    expect(calls.map((c) => c.script)).toEqual(["scripts/save_projection_csv_import.py", "scripts/run_projection_adjustment.py"]);
    expect(argValue(calls[0].args, "--original-filename")).toBe("bluecollar.csv");
  });

  it("does not run the adjustment layer when the save itself fails (no_players)", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({ "scripts/save_projection_csv_import.py": () => ok(JSON.stringify({ status: "no_players", reason: "No row had both a name and a projection." })) }, calls),
    );

    const { saveProjectionCsvImport } = await import("../csvImport");
    const result = await saveProjectionCsvImport(Buffer.from("a,b\n\n"), "bluecollar", DATE, "empty.csv");

    expect(result.status).toBe("no_players");
    expect(calls).toHaveLength(1);
  });

  it("still returns the save result when the adjustment layer has no research package yet", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/save_projection_csv_import.py": () => ok(JSON.stringify({ status: "ready", path: "x.json", player_count: 5, provider_name: "Custom CSV" })),
          "scripts/run_projection_adjustment.py": () => ok(JSON.stringify({ status: "no_research", reason: "No pitcher or batter snapshot found." })),
        },
        calls,
      ),
    );

    const { saveProjectionCsvImport } = await import("../csvImport");
    const result = await saveProjectionCsvImport(Buffer.from("Name,Proj\nAce,10\n"), "custom_csv", DATE, "x.csv");

    expect(result.status).toBe("ready");
    expect(result.adjustment).toEqual({ status: "no_research", record_count: undefined, reason: "No pitcher or batter snapshot found." });
  });
});

describe("listProjectionImports / deleteProjectionImport / activateProjectionImport", () => {
  it("lists imports for a date", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner({ "scripts/list_projection_imports.py": () => ok(JSON.stringify({ status: "ok", slate_date: DATE, imports: [{ path: "x.json", is_active: true }] })) }, calls),
    );

    const { listProjectionImports } = await import("../csvImport");
    const result = await listProjectionImports(DATE);
    expect(result).toEqual([{ path: "x.json", is_active: true }]);
  });

  it("deletes an import", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner({ "scripts/delete_projection_import.py": () => ok(JSON.stringify({ status: "ok" })) }, calls));

    const { deleteProjectionImport } = await import("../csvImport");
    const result = await deleteProjectionImport("some/path.json");
    expect(result).toEqual({ ok: true });
    expect(argValue(calls[0].args, "--path")).toBe("some/path.json");
  });

  it("surfaces a delete error (e.g. path outside the owned snapshot root)", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(makeFakeRunner({ "scripts/delete_projection_import.py": () => ok(JSON.stringify({ status: "error", reason: "Not a projection baseline snapshot file." })) }, calls));

    const { deleteProjectionImport } = await import("../csvImport");
    const result = await deleteProjectionImport("../etc/passwd");
    expect(result).toEqual({ error: "Not a projection baseline snapshot file." });
  });

  it("reactivates an import then re-runs the adjustment layer", async () => {
    const calls: Array<{ script: string; args: string[] }> = [];
    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(
      makeFakeRunner(
        {
          "scripts/reactivate_projection_import.py": () => ok(JSON.stringify({ status: "ready", path: "new.json" })),
          "scripts/run_projection_adjustment.py": () => ok(JSON.stringify({ status: "ready", record_count: 10 })),
        },
        calls,
      ),
    );

    const { activateProjectionImport } = await import("../csvImport");
    const result = await activateProjectionImport("old.json", DATE);
    expect(result).toEqual({ ok: true, path: "new.json" });
    expect(calls.map((c) => c.script)).toEqual(["scripts/reactivate_projection_import.py", "scripts/run_projection_adjustment.py"]);
  });
});

describe("resolveOwnedImportSnapshotPath", () => {
  it("accepts a path inside external_projection_snapshots/ tagged source=csv_import", async () => {
    writeJson(`external_projection_snapshots/${DATE}/provider_bluecollar_20260813T180000.json`, { source: "csv_import" });
    const { resolveOwnedImportSnapshotPath } = await import("../csvImport");
    const resolved = resolveOwnedImportSnapshotPath(path.join(tmpDir, `external_projection_snapshots/${DATE}/provider_bluecollar_20260813T180000.json`));
    expect(resolved).not.toBeNull();
  });

  it("rejects a path outside external_projection_snapshots/", async () => {
    const outside = path.join(tmpDir, "predictions", "secret.json");
    fs.mkdirSync(path.dirname(outside), { recursive: true });
    fs.writeFileSync(outside, JSON.stringify({ source: "csv_import" }));
    const { resolveOwnedImportSnapshotPath } = await import("../csvImport");
    expect(resolveOwnedImportSnapshotPath(outside)).toBeNull();
  });

  it("rejects a snapshot not tagged source=csv_import (e.g. a live provider fetch)", async () => {
    writeJson(`external_projection_snapshots/${DATE}/provider_mock_external_projections_20260813T180000.json`, { source: "provider_fetch" });
    const { resolveOwnedImportSnapshotPath } = await import("../csvImport");
    const resolved = resolveOwnedImportSnapshotPath(path.join(tmpDir, `external_projection_snapshots/${DATE}/provider_mock_external_projections_20260813T180000.json`));
    expect(resolved).toBeNull();
  });

  it("rejects a path-traversal attempt using a filename inside the root", async () => {
    const { resolveOwnedImportSnapshotPath } = await import("../csvImport");
    const traversal = path.join(tmpDir, "external_projection_snapshots", DATE, "..", "..", "..", "etc", "provider_x_1.json");
    expect(resolveOwnedImportSnapshotPath(traversal)).toBeNull();
  });
});
