import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../../lib/db/client";
import { __resetExecutorForTests } from "../../lib/db/executor";
import { parseArgs, runRefresh } from "../refresh-research-and-eligibility";

function insertCanonicalSlate(internalSlateId: string, providerSlateId: string, slateDate = "2026-09-02") {
  getDb()
    .prepare(
      `INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, schema_version, validation_state, source_provenance, created_at, updated_at)
       VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Main', ?, ?, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')`,
    )
    .run(internalSlateId, providerSlateId, slateDate, `${slateDate}T23:05:00Z`);
}

function insertCanonicalPlayer(internalSlateId: string, providerPlayerId: string) {
  getDb()
    .prepare(
      `INSERT INTO slate_players (internal_slate_id, provider_player_id, name, team, opponent, salary, position_eligibility_json, identity_status, created_at, updated_at)
       VALUES (?, ?, 'Player', 'BOS', 'TOR', 4500, '["OF"]', 'UNRESOLVED', 'x', 'x')`,
    )
    .run(internalSlateId, providerPlayerId);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

afterEach(async () => {
  const { __resetPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

describe("T3: refresh-research-and-eligibility.ts parseArgs", () => {
  it("parses --date and defaults --sport to MLB", () => {
    expect(parseArgs(["--date", "2026-09-02"])).toEqual({ date: "2026-09-02", sport: "MLB" });
  });

  it("accepts an explicit --sport", () => {
    expect(parseArgs(["--date", "2026-09-02", "--sport", "NFL"])).toEqual({ date: "2026-09-02", sport: "NFL" });
  });

  it("throws with a clear usage message when --date is missing", () => {
    expect(() => parseArgs([])).toThrow(/Usage/);
  });
});

describe("T3: runRefresh -- the automatic research/identity/eligibility orchestration", () => {
  it("runs all three real steps and reports OK for each on a healthy day", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(true);
    expect(summary.identity.ok).toBe(true);
    expect(summary.eligibility.ok).toBe(true);
    expect(summary.eligibility.slatesFound).toBe(1);
    expect(summary.eligibility.slatesUpdated).toBe(1);
  });

  it("T3 Step 5/11: a research package failure never prevents identity refresh or eligibility recompute from running", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 1, stdout: "", stderr: "MLB Stats API unreachable", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(false);
    expect(summary.research.detail).toContain("MLB Stats API unreachable");
    // The other two steps still ran and succeeded -- one failure does not cascade.
    expect(summary.identity.ok).toBe(true);
    expect(summary.eligibility.ok).toBe(true);
  });

  it("T3 Step 5/11: an identity refresh failure never prevents research refresh or eligibility recompute from running", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async (script) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 1, stdout: "", stderr: "roster fetch failed", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(true);
    expect(summary.identity.ok).toBe(false);
    expect(summary.identity.detail).toContain("roster fetch failed");
    expect(summary.eligibility.ok).toBe(true);
  });

  it("T3 Step 5/11: an eligibility recompute failure for one slate never destroys a sibling slate's good state, and never stops the whole run", async () => {
    insertCanonicalSlate("s1", "dkunofficial-1");
    insertCanonicalPlayer("s1", "1");
    insertCanonicalSlate("s2", "dkunofficial-2");
    insertCanonicalPlayer("s2", "2");
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    let callIndex = 0;
    __setPythonRunnerForTests(async (script, args) => {
      if (script === "scripts/build_research_package.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/refresh_player_identity.py") return { exitCode: 0, stdout: "ok", stderr: "", command: [] };
      if (script === "scripts/compute_canonical_eligibility.py") {
        callIndex += 1;
        // Fail the first slate's eligibility compute, succeed the second --
        // proves per-slate isolation from inside this orchestration script,
        // not just inside refreshCanonicalEligibilityForDate in isolation.
        const inputPath = args[args.indexOf("--input") + 1];
        const fs = await import("node:fs");
        const payload = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
        if (payload.date === "2026-09-02" && callIndex === 1) {
          return { exitCode: 1, stdout: "", stderr: "crash", command: [] };
        }
        return { exitCode: 0, stdout: 'RESULT_JSON:{"status":"OK","date":"2026-09-02","results":[]}', stderr: "", command: [] };
      }
      throw new Error(`Unexpected script: ${script}`);
    });

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.eligibility.slatesFound).toBe(2);
    expect(summary.eligibility.slatesFailed).toBe(1);
    expect(summary.eligibility.slatesUpdated).toBe(1);
    expect(summary.eligibility.ok).toBe(false); // honestly degraded, never hidden
  });

  it("never throws even when every step fails -- always returns a summary", async () => {
    const { __setPythonRunnerForTests } = await import("../../lib/orchestrator/pythonRunner");
    __setPythonRunnerForTests(async () => ({ exitCode: 1, stdout: "", stderr: "total outage", command: [] }));

    const summary = await runRefresh("2026-09-02", "MLB");
    expect(summary.research.ok).toBe(false);
    expect(summary.identity.ok).toBe(false);
    // Zero canonical slates exist for this date in this test's DB -- an
    // honest "nothing to do" success, never fabricated.
    expect(summary.eligibility.slatesFound).toBe(0);
  });
});
