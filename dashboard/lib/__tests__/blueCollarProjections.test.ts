import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-23";
const SLATE_ID = "dkunofficial-152551";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function bcPlayerRecord(overrides: Record<string, unknown> = {}) {
  return {
    bluecollar_local_id: "cristopher-sanchez|phi|p",
    name: "Cristopher Sanchez",
    team: "PHI",
    position: "P",
    opponent: "STL",
    salary: 11800,
    raw_projection: 19.5,
    usable_projection: 19.5,
    match_status: "matched",
    match_confidence: "name_team_exact",
    mlb_player_id: "650911",
    candidate_mlb_ids: [],
    candidate_names: [],
    ...overrides,
  };
}

function snapshotDoc(overrides: Record<string, unknown> = {}) {
  return {
    slate_date: DATE, dk_slate_id: SLATE_ID, bluecollar_slate_id: "bluecollar-main",
    bluecollar_slate_name: "1:35PM ET Main 8 Games", bluecollar_updated: "12:36:44 ET",
    retrieved_at: "2026-08-23T17:06:18Z", slate_match_status: "matched", slate_match_reason: null,
    player_count: 746, matched_count: 15, usable_projection_count: 159, players: [],
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-bluecollar-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestBlueCollarSnapshot", () => {
  it("returns null when no slateId is given -- BlueCollar is always slate-scoped, never date-only", async () => {
    const { loadLatestBlueCollarSnapshot } = await import("../blueCollarProjections");
    expect(loadLatestBlueCollarSnapshot(DATE, null)).toBeNull();
  });

  it("returns null when no snapshot exists -- never throws", async () => {
    const { loadLatestBlueCollarSnapshot } = await import("../blueCollarProjections");
    expect(loadLatestBlueCollarSnapshot(DATE, SLATE_ID)).toBeNull();
  });

  it("returns the latest snapshot by filename timestamp, scoped to the slate", async () => {
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T170000.json`, snapshotDoc({ retrieved_at: "2026-08-23T17:00:00Z", usable_projection_count: 100 }));
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T180000.json`, snapshotDoc({ retrieved_at: "2026-08-23T18:00:00Z", usable_projection_count: 159 }));
    const { loadLatestBlueCollarSnapshot } = await import("../blueCollarProjections");
    const latest = loadLatestBlueCollarSnapshot(DATE, SLATE_ID);
    expect(latest?.retrieved_at).toBe("2026-08-23T18:00:00Z");
    expect(latest?.usable_projection_count).toBe(159);
  });

  it("never leaks another DK slate's snapshot -- two slates sharing a date stay isolated", async () => {
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T170000.json`, snapshotDoc({ dk_slate_id: SLATE_ID, bluecollar_slate_name: "Main" }));
    writeJson(`bluecollar_projection_snapshots/${DATE}/dkunofficial-turbo/bluecollar_projection_20260823T170500.json`, snapshotDoc({ dk_slate_id: "dkunofficial-turbo", bluecollar_slate_name: "Turbo" }));
    const { loadLatestBlueCollarSnapshot } = await import("../blueCollarProjections");
    expect(loadLatestBlueCollarSnapshot(DATE, SLATE_ID)?.bluecollar_slate_name).toBe("Main");
    expect(loadLatestBlueCollarSnapshot(DATE, "dkunofficial-turbo")?.bluecollar_slate_name).toBe("Turbo");
  });

  it("never contains an api_key field, regardless of what's on disk", async () => {
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T170000.json`, snapshotDoc({ players: [bcPlayerRecord()] }));
    const { loadLatestBlueCollarSnapshot } = await import("../blueCollarProjections");
    const snapshot = loadLatestBlueCollarSnapshot(DATE, SLATE_ID);
    expect(JSON.stringify(snapshot)).not.toMatch(/api[_-]?key/i);
  });
});

describe("getBlueCollarProjectionByPlayerId", () => {
  it("returns an empty map (never throws) when no snapshot exists", async () => {
    const { getBlueCollarProjectionByPlayerId } = await import("../blueCollarProjections");
    expect(getBlueCollarProjectionByPlayerId(DATE, SLATE_ID).size).toBe(0);
  });

  it("returns an empty map when slateId is null", async () => {
    const { getBlueCollarProjectionByPlayerId } = await import("../blueCollarProjections");
    expect(getBlueCollarProjectionByPlayerId(DATE, null).size).toBe(0);
  });

  it("builds a map keyed by mlb_player_id, for MATCHED players only", async () => {
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T170000.json`, snapshotDoc({
      players: [
        bcPlayerRecord(),
        bcPlayerRecord({ bluecollar_local_id: "unmatched-guy|xxx|of", name: "Unmatched Guy", mlb_player_id: null, match_status: "unmatched", match_confidence: null }),
      ],
    }));
    const { getBlueCollarProjectionByPlayerId } = await import("../blueCollarProjections");
    const map = getBlueCollarProjectionByPlayerId(DATE, SLATE_ID);
    expect(map.size).toBe(1);
    const player = map.get("650911");
    expect(player?.usable_projection).toBe(19.5);
    expect(player?.match_status).toBe("matched");
  });

  it("excludes an ambiguous match even if it happens to carry an mlb_player_id", async () => {
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T170000.json`, snapshotDoc({
      players: [bcPlayerRecord({ match_status: "ambiguous" })],
    }));
    const { getBlueCollarProjectionByPlayerId } = await import("../blueCollarProjections");
    expect(getBlueCollarProjectionByPlayerId(DATE, SLATE_ID).size).toBe(0);
  });

  it("preserves usable_projection as null (NOT AVAILABLE) without coercing to zero", async () => {
    writeJson(`bluecollar_projection_snapshots/${DATE}/${SLATE_ID}/bluecollar_projection_20260823T170000.json`, snapshotDoc({
      players: [bcPlayerRecord({ raw_projection: 0.0, usable_projection: null })],
    }));
    const { getBlueCollarProjectionByPlayerId } = await import("../blueCollarProjections");
    const player = getBlueCollarProjectionByPlayerId(DATE, SLATE_ID).get("650911");
    expect(player?.usable_projection).toBeNull();
    expect(player?.raw_projection).toBe(0.0);
  });
});
