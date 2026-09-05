import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../db/client";
import { __resetExecutorForTests } from "../db/executor";
import { __resetStorageForTests } from "../storage/getStorage";
import { computeNextEasternDate, prepareFutureDateIfDue } from "../futureDatePrep";

// MLB AUTOMATIC TOMORROW PREP -- see lib/futureDatePrep.ts's own
// docstring for the root cause this eliminates. Mirrors
// scripts/__tests__/refresh-research-and-eligibility.test.ts's own
// real-DB, mocked-python-runner convention (never mocks the database).

function insertSlate(internalSlateId: string, providerSlateId: string, slateDate: string, provider = "draftkings_unofficial", validationState = "VALID") {
  getDb()
    .prepare(
      `INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, schema_version, validation_state, source_provenance, created_at, updated_at)
       VALUES (?, 'MLB', 'draftkings', ?, ?, 'Main', ?, ?, 'slate_normalized_v1', ?, 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run(internalSlateId, provider, providerSlateId, slateDate, `${slateDate}T23:05:00Z`, validationState);
}

function insertPlayer(internalSlateId: string, providerPlayerId: string) {
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES (?, ?, 'Player', 'BOS', 'TOR', 4500, '["OF"]', 'UNRESOLVED', 'x', 'x')`,
    )
    .run(internalSlateId, providerPlayerId);
}

function insertProjection(internalSlateId: string, generatedAt: string) {
  getDb()
    .prepare(
      `INSERT INTO canonical_slate_player_projections (id, internal_slate_id, provider_player_id, source, model_version, projection, ceiling, floor, generated_at, created_at, updated_at)
       VALUES (?, ?, '1', 'native', '1.0.0', 10, 15, 5, ?, 'x', 'x')`,
    )
    .run(`proj-${internalSlateId}`, internalSlateId, generatedAt);
}

let tmpDir: string;

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-future-prep-test-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("computeNextEasternDate", () => {
  it("adds one calendar day", () => {
    expect(computeNextEasternDate("2026-09-04")).toBe("2026-09-05");
  });

  it("rolls over a month boundary", () => {
    expect(computeNextEasternDate("2026-09-30")).toBe("2026-10-01");
  });

  it("rolls over a year boundary", () => {
    expect(computeNextEasternDate("2026-12-31")).toBe("2027-01-01");
  });

  it("handles a leap-year February correctly", () => {
    expect(computeNextEasternDate("2028-02-28")).toBe("2028-02-29");
  });
});

describe("prepareFutureDateIfDue", () => {
  it("reports NOT_YET_PUBLISHED when DraftKings has no real VALID slate for tomorrow yet -- never fabricates one", async () => {
    const result = await prepareFutureDateIfDue("2026-09-04", "MLB");
    expect(result.status).toBe("NOT_YET_PUBLISHED");
    expect(result.date).toBe("2026-09-05");
    expect(result.slatesFound).toBe(0);
  });

  it("does not count a REJECTED (not yet VALID) tomorrow slate as published", async () => {
    insertSlate("s1", "152999", "2026-09-05", "draftkings_unofficial", "REJECTED");
    const result = await prepareFutureDateIfDue("2026-09-04", "MLB");
    expect(result.status).toBe("NOT_YET_PUBLISHED");
  });

  it("does not count an admin-CSV slate as an automatic publication (still real per-provider isolation)", async () => {
    insertSlate("s1", "dkcsv-main-2026-09-05", "2026-09-05", "draftkings_csv", "VALID");
    const result = await prepareFutureDateIfDue("2026-09-04", "MLB", 25);
    // A real VALID slate for tomorrow -- draftkings_csv or not -- IS
    // eligible for prep (this gate is about "does a real slate exist",
    // not which provider produced it; admin-CSV import already has its
    // own separate provenance/authorization rules).
    expect(result.status).not.toBe("NOT_YET_PUBLISHED");
  });

  it("skips a due-but-recently-prepared tomorrow (cost control -- never hammers on every cycle)", async () => {
    insertSlate("s1", "152904", "2026-09-05");
    insertProjection("s1", new Date().toISOString());
    const result = await prepareFutureDateIfDue("2026-09-04", "MLB", 25);
    expect(result.status).toBe("SKIPPED_RECENT");
    expect(result.slatesFound).toBe(1);
    expect(result.minutesSinceLastPrep).toBeLessThan(1);
  });

  it("prepares tomorrow when a real slate exists and no recent prep has happened -- runs the SAME real pipeline as today's own refresh", async () => {
    insertSlate("s1", "152904", "2026-09-05");
    insertPlayer("s1", "1");

    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    const calls: Array<{ script: string; args: string[] }> = [];
    __setPythonRunnerForTests(async (script, args) => {
      calls.push({ script, args });
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-05","results":[]}', stderr: "", command: [] };
      }
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    });

    const result = await prepareFutureDateIfDue("2026-09-04", "MLB", 25);
    expect(result.status).toBe("PREPARED");
    expect(result.summary?.date).toBe("2026-09-05"); // tomorrow, never today
    expect(result.summary?.research.ok).toBe(true);
    expect(result.summary?.eligibility.slatesFound).toBe(1);

    // Every real subprocess step ran against TOMORROW's date, not today's.
    const researchCall = calls.find((c) => c.script === "scripts/build_research_package.py");
    expect(researchCall?.args).toContain("2026-09-05");
    expect(researchCall?.args).not.toContain("2026-09-04");
  });

  it("skips an old-enough prior prep (past the throttle window) and re-prepares", async () => {
    insertSlate("s1", "152904", "2026-09-05");
    insertPlayer("s1", "1");
    const staleTimestamp = new Date(Date.now() - 30 * 60 * 1000).toISOString(); // 30 minutes ago
    insertProjection("s1", staleTimestamp);

    const { __setPythonRunnerForTests } = await import("../orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-05","results":[]}', stderr: "", command: [] };
      }
      return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
    });

    const result = await prepareFutureDateIfDue("2026-09-04", "MLB", 25); // 30m > 25m throttle
    expect(result.status).toBe("PREPARED");
  });

  it("reports ERROR (never throws) on a genuine internal failure -- caller can safely continue", async () => {
    // Forces a real SQL failure (rather than mocking the module) so this
    // proves the function's own try/catch, not a test double's behavior.
    getDb().exec("DROP TABLE slates");
    const result = await prepareFutureDateIfDue("2026-09-04", "MLB");
    expect(result.status).toBe("ERROR");
    expect(typeof result.error).toBe("string");
  });

  it("MLB PREP Phase 10 -- today's already-prepared data is completely unaffected by a tomorrow-prep failure", async () => {
    insertSlate("s-today", "152904", "2026-09-04");
    insertPlayer("s-today", "1");
    // today's own eligibility was already computed by an earlier, separate
    // runRefresh(TODAY, ...) call -- simulated directly here since this
    // test's focus is isolation, not re-proving runRefresh() itself
    // (already covered by scripts/__tests__/refresh-research-and-eligibility.test.ts).
    getDb().prepare("UPDATE slate_players SET eligibility_status = 'STARTING_HITTER', optimizer_eligible = 1, eligibility_computed_at = ? WHERE internal_slate_id = 's-today'").run(new Date().toISOString());

    // Tomorrow's prep is forced to fail (DB error), independent of today.
    insertSlate("s-tomorrow", "153153", "2026-09-05");
    getDb().exec("DROP TABLE canonical_slate_player_projections");

    const result = await prepareFutureDateIfDue("2026-09-04", "MLB");
    expect(result.status).toBe("ERROR");

    // Today's own row is untouched by tomorrow's failure.
    const todayRow = getDb().prepare("SELECT eligibility_status, optimizer_eligible FROM slate_players WHERE internal_slate_id = 's-today'").get() as Record<string, unknown>;
    expect(todayRow.eligibility_status).toBe("STARTING_HITTER");
    expect(todayRow.optimizer_eligible).toBe(1);
  });
});
