import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  findAllFiles,
  findLatestFile,
  latestSlateDate,
  listSlateDates,
  safeListDir,
  safeReadJson,
} from "../discovery";

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-dashboard-test-"));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("safeListDir", () => {
  it("returns an empty array for a missing directory instead of throwing", () => {
    expect(safeListDir(path.join(tmpDir, "does-not-exist"))).toEqual([]);
  });

  it("lists real files sorted", () => {
    fs.writeFileSync(path.join(tmpDir, "b.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "a.json"), "{}");
    expect(safeListDir(tmpDir)).toEqual(["a.json", "b.json"]);
  });
});

describe("findLatestFile", () => {
  it("returns null when no file matches the prefix", () => {
    expect(findLatestFile(tmpDir, "pitcher_board_")).toBeNull();
  });

  it("returns the lexically-latest matching file (timestamp-sortable filenames)", () => {
    fs.writeFileSync(path.join(tmpDir, "pitcher_board_20260805T100000.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "pitcher_board_20260805T235900.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "batter_board_20260805T999999.json"), "{}"); // different prefix
    const latest = findLatestFile(tmpDir, "pitcher_board_");
    expect(latest).toBe(path.join(tmpDir, "pitcher_board_20260805T235900.json"));
  });

  it("respects the extension filter", () => {
    fs.writeFileSync(path.join(tmpDir, "dk_lineups_1.csv"), "a,b\n");
    fs.writeFileSync(path.join(tmpDir, "dk_lineups_1.json"), "{}");
    expect(findLatestFile(tmpDir, "dk_lineups_", ".csv")).toBe(path.join(tmpDir, "dk_lineups_1.csv"));
  });
});

describe("findAllFiles", () => {
  it("returns every matching file, not just the latest", () => {
    fs.writeFileSync(path.join(tmpDir, "contest_1_ownership_eval_a.json"), "{}");
    fs.writeFileSync(path.join(tmpDir, "contest_2_ownership_eval_b.json"), "{}");
    expect(findAllFiles(tmpDir, "contest_")).toHaveLength(2);
  });

  it("returns an empty array for a missing directory", () => {
    expect(findAllFiles(path.join(tmpDir, "nope"), "x")).toEqual([]);
  });
});

describe("listSlateDates / latestSlateDate", () => {
  it("only picks up YYYY-MM-DD directories, newest first", () => {
    fs.mkdirSync(path.join(tmpDir, "2026-08-05"));
    fs.mkdirSync(path.join(tmpDir, "2026-08-11"));
    fs.mkdirSync(path.join(tmpDir, "raw")); // not a date -- must be excluded
    expect(listSlateDates(tmpDir)).toEqual(["2026-08-11", "2026-08-05"]);
    expect(latestSlateDate(tmpDir)).toBe("2026-08-11");
  });

  it("returns null when no slate directories exist", () => {
    expect(latestSlateDate(tmpDir)).toBeNull();
  });
});

describe("safeReadJson", () => {
  it("returns null for a null path", () => {
    expect(safeReadJson(null)).toBeNull();
  });

  it("returns null for a missing file instead of throwing", () => {
    expect(safeReadJson(path.join(tmpDir, "missing.json"))).toBeNull();
  });

  it("returns null for malformed JSON instead of throwing", () => {
    const p = path.join(tmpDir, "bad.json");
    fs.writeFileSync(p, "{not valid json");
    expect(safeReadJson(p)).toBeNull();
  });

  it("parses valid JSON", () => {
    const p = path.join(tmpDir, "good.json");
    fs.writeFileSync(p, JSON.stringify({ a: 1 }));
    expect(safeReadJson<{ a: number }>(p)).toEqual({ a: 1 });
  });
});
