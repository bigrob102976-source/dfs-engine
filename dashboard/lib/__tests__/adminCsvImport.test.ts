import fs from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests, getDb } from "../db/client";
import { __resetExecutorForTests } from "../db/executor";
import { __resetStorageForTests } from "../storage/getStorage";
import {
  deactivateAdminCsvSlate,
  findAutomaticSlateCollision,
  importDkCsvToCanonical,
  validateDkCsvUpload,
} from "../adminCsvImport";

// Real end-to-end behavior tests -- BREAK-GLASS ADMIN CSV UPLOAD. Calls
// lib/adminCsvImport.ts's functions directly with plain Buffer/string
// arguments (never through an HTTP Request/FormData -- see
// app/api/admin/slate-import/__tests__/accessControl.test.ts's own note
// on why that layer's tests are auth-only under this project's jsdom
// test environment). Exercises the REAL Python CLI scripts (no
// pythonRunner mock) and REAL canonical Postgres-shape persistence (a
// fresh SQLite test DB with migrations applied), matching this
// project's established "don't mock the database" testing convention
// (see app/api/dfs-salaries/__tests__/accessControl.test.ts's own
// unmocked "ADMIN reaches the real handler" case).
//
// Deliberately does NOT override MLB_DFS_ROOT: lib/orchestrator/pythonRunner.ts
// spawns the real `python` executable with cwd = getArtifactRoot(), so
// scripts/validate_dk_csv_upload.py etc. must be resolved against the
// REAL repo root, not an empty temp dir (which would make python fail
// to even find the script). This means these tests write real files
// under the real repo's dfs_input/raw/normalized trees for the two
// obviously-fake test dates below -- afterEach removes exactly those,
// so the repo is left clean.

const TEST_SLATE_DATE = "2099-06-15"; // obviously-fake, never a real production date
const OTHER_DATE = "2099-06-14";

const REAL_CSV = (
  "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n" +
  "SP,Ace Pitcher (5001),Ace Pitcher,5001,SP,9500,TOR@BOS 07:05PM ET,TOR,22.1\n" +
  "OF,Lead Off (5002),Lead Off,5002,OF,4200,TOR@BOS 07:05PM ET,BOS,9.4\n" +
  "1B,First Baseman (5003),First Baseman,5003,1B,4800,TOR@BOS 07:05PM ET,BOS,10.1\n" +
  "3B,Third Baseman (5004),Third Baseman,5004,3B,3600,TOR@BOS 07:05PM ET,TOR,7.8\n"
);

function insertAutomaticSlate(internalSlateId: string, providerSlateId: string, date: string) {
  getDb()
    .prepare(
      "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, schema_version, validation_state, source_provenance, created_at, updated_at) " +
        "VALUES (?, 'MLB', 'draftkings', 'draftkings_unofficial', ?, 'Main', ?, ?, 'slate_normalized_v1', 'VALID', 'DRAFTKINGS_UNOFFICIAL_LIVE', 'x', 'x')",
    )
    .run(internalSlateId, providerSlateId, date, `${date}T23:05:00Z`);
}

const REPO_ROOT = path.resolve(process.cwd(), "..");

function rmTestArtifacts() {
  for (const date of [TEST_SLATE_DATE, OTHER_DATE]) {
    for (const dir of [
      path.join(REPO_ROOT, "dfs_input", date),
      path.join(REPO_ROOT, "raw", "MLB", date),
      path.join(REPO_ROOT, "normalized", "MLB", date),
    ]) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  __resetStorageForTests();
  rmTestArtifacts();
});

afterEach(() => {
  rmTestArtifacts();
});

describe("validateDkCsvUpload -- Phase 2/3/12", () => {
  it("a real, well-formed DK CSV is reported valid with an accurate preview", async () => {
    const result = await validateDkCsvUpload(Buffer.from(REAL_CSV));
    expect(result.status).toBe("valid");
    expect(result.playerCount).toBe(4);
    expect(result.salaryMin).toBe(3600);
    expect(result.salaryMax).toBe(9500);
    expect(result.teams?.slice().sort()).toEqual(["BOS", "TOR"]);
    expect(result.duplicatePlayerIds).toEqual([]);
  });

  it("a structurally invalid CSV is rejected with a clear reason, never crashes", async () => {
    const result = await validateDkCsvUpload(Buffer.from("not,a,real,dk,csv\n1,2,3,4,5\n"));
    expect(result.status).toBe("invalid");
    expect(typeof result.reason).toBe("string");
  });

  it("an empty file is rejected", async () => {
    const result = await validateDkCsvUpload(Buffer.from(""));
    expect(result.status).toBe("invalid");
  });

  it("duplicate DK player IDs are flagged, never silently deduplicated", async () => {
    const csvText =
      "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n" +
      "OF,Player One (1),Player One,1,OF,4500,TOR@BOS,BOS,10.0\n" +
      "OF,Player One Dup (1),Player One,1,OF,4600,TOR@BOS,BOS,10.0\n";
    const result = await validateDkCsvUpload(Buffer.from(csvText));
    expect(result.status).toBe("valid");
    expect(result.duplicatePlayerIds).toEqual(["1"]);
  });
});

describe("findAutomaticSlateCollision -- Phase 6", () => {
  it("finds a real automatic (non-CSV) slate for the same date", async () => {
    insertAutomaticSlate("auto-1", "152904", TEST_SLATE_DATE);
    const collisions = await findAutomaticSlateCollision(TEST_SLATE_DATE, "MLB");
    expect(collisions).toHaveLength(1);
    expect(collisions[0].providerSlateId).toBe("152904");
    expect(collisions[0].provider).toBe("draftkings_unofficial");
  });

  it("reports no collision when only a draftkings_csv slate exists for the date", async () => {
    getDb()
      .prepare(
        "INSERT INTO slates (internal_slate_id, sport, site, provider, provider_slate_id, slate_name, slate_date, first_game_start_utc, schema_version, validation_state, source_provenance, created_at, updated_at) " +
          "VALUES ('csv-1', 'MLB', 'draftkings', 'draftkings_csv', 'dkcsv-main', ?, ?, ?, 'slate_normalized_v1', 'VALID', 'OFFICIAL_USER_UPLOAD', 'x', 'x')",
      )
      .run("Main", TEST_SLATE_DATE, `${TEST_SLATE_DATE}T18:00:00Z`);
    const collisions = await findAutomaticSlateCollision(TEST_SLATE_DATE, "MLB");
    expect(collisions).toEqual([]);
  });

  it("reports no collision for a different date", async () => {
    insertAutomaticSlate("auto-1", "152904", OTHER_DATE);
    const collisions = await findAutomaticSlateCollision(TEST_SLATE_DATE, "MLB");
    expect(collisions).toEqual([]);
  });
});

describe("importDkCsvToCanonical -- Phase 4/5/12", () => {
  it("promotes a real CSV to canonical Postgres with OFFICIAL_USER_UPLOAD provenance, never DRAFTKINGS_UNOFFICIAL_LIVE", async () => {
    const result = await importDkCsvToCanonical(Buffer.from(REAL_CSV), TEST_SLATE_DATE, "Main", "DKSalaries.csv");
    expect(result.ok).toBe(true);
    expect(result.internalSlateId).toBeTruthy();
    expect(result.sourceProvenance).toBe("OFFICIAL_USER_UPLOAD");
    expect(result.sourceProvenance).not.toBe("DRAFTKINGS_UNOFFICIAL_LIVE");
    expect(result.validationState).toBe("VALID");
    expect(result.playerCount).toBe(4);

    const row = getDb()
      .prepare("SELECT provider, provider_slate_id, source_provenance, validation_state FROM slates WHERE internal_slate_id = ?")
      .get(result.internalSlateId!) as Record<string, unknown>;
    expect(row.provider).toBe("draftkings_csv");
    expect(row.source_provenance).toBe("OFFICIAL_USER_UPLOAD");
    expect(row.validation_state).toBe("VALID");
    // Never collides with a real DraftGroup-ID-shaped identity.
    expect(row.provider_slate_id).toMatch(/^dkcsv-/);

    const playerRows = getDb().prepare("SELECT COUNT(*) as n FROM slate_players WHERE internal_slate_id = ?").get(result.internalSlateId!) as { n: number };
    expect(playerRows.n).toBe(4);
  });

  it("a structurally invalid CSV is never promoted -- import fails cleanly, nothing written to slates", async () => {
    const result = await importDkCsvToCanonical(Buffer.from("not,a,real,dk,csv\n"), TEST_SLATE_DATE, "Main", "bad.csv");
    expect(result.ok).toBe(false);
    expect(typeof result.reason).toBe("string");

    const count = getDb().prepare("SELECT COUNT(*) as n FROM slates").get() as { n: number };
    expect(count.n).toBe(0);
  });

  it("importing twice for the same date/label updates the SAME canonical slate identity, never duplicates it", async () => {
    const first = await importDkCsvToCanonical(Buffer.from(REAL_CSV), TEST_SLATE_DATE, "Main", "DKSalaries.csv");
    expect(first.ok).toBe(true);

    const updatedCsv = REAL_CSV.replace("9500", "9600");
    const second = await importDkCsvToCanonical(Buffer.from(updatedCsv), TEST_SLATE_DATE, "Main", "DKSalaries2.csv");
    expect(second.ok).toBe(true);
    expect(second.internalSlateId).toBe(first.internalSlateId);

    const count = getDb().prepare("SELECT COUNT(*) as n FROM slates WHERE provider = 'draftkings_csv'").get() as { n: number };
    expect(count.n).toBe(1);
  });

  it("does not overwrite or alter a real automatic slate for the same date -- distinct provider identity", async () => {
    insertAutomaticSlate("auto-1", "152904", TEST_SLATE_DATE);
    const result = await importDkCsvToCanonical(Buffer.from(REAL_CSV), TEST_SLATE_DATE, "Main", "DKSalaries.csv");
    expect(result.ok).toBe(true);
    expect(result.internalSlateId).not.toBe("auto-1");

    const autoRow = getDb().prepare("SELECT provider, provider_slate_id, validation_state FROM slates WHERE internal_slate_id = 'auto-1'").get() as Record<string, unknown>;
    expect(autoRow.provider).toBe("draftkings_unofficial");
    expect(autoRow.provider_slate_id).toBe("152904");
    expect(autoRow.validation_state).toBe("VALID");

    const both = getDb().prepare("SELECT provider FROM slates WHERE slate_date = ?").all(TEST_SLATE_DATE) as Array<Record<string, unknown>>;
    expect(both).toHaveLength(2);
  });
});

describe("deactivateAdminCsvSlate -- Phase 9", () => {
  it("flips validationState to REJECTED without deleting the row", async () => {
    const imported = await importDkCsvToCanonical(Buffer.from(REAL_CSV), TEST_SLATE_DATE, "Main", "DKSalaries.csv");
    expect(imported.ok).toBe(true);

    const result = await deactivateAdminCsvSlate(imported.internalSlateId!);
    expect(result.ok).toBe(true);

    const row = getDb().prepare("SELECT validation_state FROM slates WHERE internal_slate_id = ?").get(imported.internalSlateId!) as Record<string, unknown>;
    expect(row.validation_state).toBe("REJECTED");
    expect(row).toBeTruthy(); // row still exists

    const playerRows = getDb().prepare("SELECT COUNT(*) as n FROM slate_players WHERE internal_slate_id = ?").get(imported.internalSlateId!) as { n: number };
    expect(playerRows.n).toBe(4); // player history preserved
  });

  it("refuses to touch a real automatic slate even when given its internalSlateId directly", async () => {
    insertAutomaticSlate("auto-1", "152904", TEST_SLATE_DATE);
    const result = await deactivateAdminCsvSlate("auto-1");
    expect(result.ok).toBe(false);

    const row = getDb().prepare("SELECT validation_state FROM slates WHERE internal_slate_id = 'auto-1'").get() as Record<string, unknown>;
    expect(row.validation_state).toBe("VALID");
  });

  it("reports failure for a nonexistent internalSlateId", async () => {
    const result = await deactivateAdminCsvSlate("does-not-exist");
    expect(result.ok).toBe(false);
  });
});
