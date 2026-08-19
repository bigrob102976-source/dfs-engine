import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-19";
const SLATE_ID = "dkcsv-main-2026-08-19";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function writePool(overrides: Record<string, unknown> = {}) {
  writeJson(`dfs_input/${DATE}/dk_player_pool_20260819T200000.json`, {
    slate_date: DATE, selected_slate_id: SLATE_ID, player_count: 1,
    players: [{ dk_player_id: "1", name: "X", team: "AAA", mlb_player_id: "111", player_type: "hitter" }],
    ...overrides,
  });
}

function writeMatchReport(overrides: Record<string, unknown> = {}) {
  writeJson(`dfs_input/${DATE}/dk_match_report_20260819T200000.json`, {
    dk_entries: 1, dk_games_total: 1, dk_games_matched_to_research: 1,
    source_provenance: "OFFICIAL_USER_UPLOAD",
    identity_integrity: { total: 1, valid: 1, warning: 0, invalid: 0 },
    ...overrides,
  });
}

function writeNative() {
  writeJson(`native_projection_snapshots/${DATE}/native_projection_20260819T200000.json`, {
    slate_date: DATE, generated_at: "x", model_version: "1.0.0", player_count: 1,
    players: [{ player_id: "111", name: "X", team: "AAA", player_type: "hitter", opponent: null, game_id: null, salary: null,
      positions: [], batting_order: null, native_projection: 8, native_ceiling: 12, native_floor: 4, confidence: 80,
      variance: 1, model_version: "1.0.0", input_coverage: { fields_available: 1, fields_total: 1, missing_fields: [], fraction: 1 },
      reasons: [], generated_at: "x" }],
    warnings: [],
  });
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-publishreadiness-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("evaluatePublishReadiness", () => {
  it("is not ok when nothing has been built yet", async () => {
    const { evaluatePublishReadiness } = await import("../slatePublishReadiness");
    const readiness = evaluatePublishReadiness(DATE, SLATE_ID);
    expect(readiness.ok).toBe(false);
    expect(readiness.required.every((c) => !c.ok)).toBe(true);
  });

  it("is ok once all required signals are present, even with every optional signal missing", async () => {
    writePool();
    writeMatchReport();
    writeNative();
    const { evaluatePublishReadiness } = await import("../slatePublishReadiness");
    const readiness = evaluatePublishReadiness(DATE, SLATE_ID);
    expect(readiness.ok).toBe(true);
    expect(readiness.required.every((c) => c.ok)).toBe(true);
    // Optional signals honestly reported missing, never fabricated as ready.
    expect(readiness.optional.find((c) => c.key === "vegas")!.ok).toBe(false);
    expect(readiness.optional.find((c) => c.key === "ai_projections")!.ok).toBe(false);
    expect(readiness.optional.find((c) => c.key === "ownership")!.ok).toBe(false);
  });

  it("blocks on untrusted source provenance even when everything else is ready", async () => {
    writePool();
    writeMatchReport({ source_provenance: "SYNTHETIC_VALIDATION" });
    writeNative();
    const { evaluatePublishReadiness } = await import("../slatePublishReadiness");
    const readiness = evaluatePublishReadiness(DATE, SLATE_ID);
    expect(readiness.ok).toBe(false);
    expect(readiness.required.find((c) => c.key === "source_provenance")!.ok).toBe(false);
  });

  it("blocks when identity integrity has invalid rows", async () => {
    writePool();
    writeMatchReport({ identity_integrity: { total: 5, valid: 3, warning: 0, invalid: 2 } });
    writeNative();
    const { evaluatePublishReadiness } = await import("../slatePublishReadiness");
    const readiness = evaluatePublishReadiness(DATE, SLATE_ID);
    expect(readiness.ok).toBe(false);
    expect(readiness.required.find((c) => c.key === "pool_integrity")!.ok).toBe(false);
  });

  it("blocks when native projections are missing", async () => {
    writePool();
    writeMatchReport();
    const { evaluatePublishReadiness } = await import("../slatePublishReadiness");
    const readiness = evaluatePublishReadiness(DATE, SLATE_ID);
    expect(readiness.ok).toBe(false);
    expect(readiness.required.find((c) => c.key === "native_projections")!.ok).toBe(false);
  });

  it("blocks when game resolution failed", async () => {
    writePool();
    writeMatchReport({ dk_games_total: 3, dk_games_matched_to_research: 0 });
    writeNative();
    const { evaluatePublishReadiness } = await import("../slatePublishReadiness");
    const readiness = evaluatePublishReadiness(DATE, SLATE_ID);
    expect(readiness.ok).toBe(false);
    expect(readiness.required.find((c) => c.key === "game_resolution")!.ok).toBe(false);
  });
});
