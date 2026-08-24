import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import {
  archiveSlate,
  effectiveDisplayStatus,
  getPublishedVersion,
  getSlateStatus,
  listPublishedSlateIds,
  listPublishHistory,
  listSlateStatuses,
  publishSlateRecord,
  unpublishSlate,
  upsertSlateStatus,
} from "../slateStatus";
import { createUser } from "../users";

const DATE = "2026-08-19";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

async function adminId(): Promise<string> {
  return (await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" })).id;
}

describe("slate_status upsert", () => {
  it("creates a DRAFT row on first upsert", async () => {
    const row = await upsertSlateStatus(DATE, "main", { slateLabel: "Main", status: "DRAFT" });
    expect(row.status).toBe("DRAFT");
    expect(row.slate_label).toBe("Main");
  });

  it("transitions DRAFT -> PROCESSING -> READY, preserving unspecified fields", async () => {
    await upsertSlateStatus(DATE, "main", { slateLabel: "Main", status: "DRAFT" });
    await upsertSlateStatus(DATE, "main", { status: "PROCESSING" });
    const ready = await upsertSlateStatus(DATE, "main", { status: "READY", poolPath: "dfs_input/x/pool.json" });
    expect(ready.status).toBe("READY");
    expect(ready.slate_label).toBe("Main"); // preserved from the first upsert
    expect(ready.pool_path).toBe("dfs_input/x/pool.json");
  });

  it("M32.7: persists and updates change_report_json, preserving it across an unrelated upsert", async () => {
    const withReport = await upsertSlateStatus(DATE, "main", { status: "READY", changeReportJson: JSON.stringify({ lineupsPosted: 2 }) });
    expect(JSON.parse(withReport.change_report_json!)).toEqual({ lineupsPosted: 2 });

    // An upsert that doesn't touch changeReportJson preserves it (same
    // "only fields present in patch are changed" discipline as every
    // other column here).
    const unrelated = await upsertSlateStatus(DATE, "main", { status: "PROCESSING" });
    expect(JSON.parse(unrelated.change_report_json!)).toEqual({ lineupsPosted: 2 });

    // A later refresh's own report replaces the prior one.
    const updated = await upsertSlateStatus(DATE, "main", { status: "READY", changeReportJson: JSON.stringify({ lineupsPosted: 0 }) });
    expect(JSON.parse(updated.change_report_json!)).toEqual({ lineupsPosted: 0 });
  });

  it("listSlateStatuses returns every slate for a date, sorted by slate_id", async () => {
    await upsertSlateStatus(DATE, "turbo", { status: "DRAFT" });
    await upsertSlateStatus(DATE, "main", { status: "DRAFT" });
    const rows = await listSlateStatuses(DATE);
    expect(rows.map((r) => r.slate_id)).toEqual(["main", "turbo"]);
  });

  it("getSlateStatus returns null for an unknown slate", async () => {
    expect(await getSlateStatus(DATE, "nope")).toBeNull();
  });
});

describe("publishSlateRecord", () => {
  it("publishing sets status PUBLISHED and pins the given snapshot paths", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: "pool.json", matchReportPath: "report.json", ownershipPath: "own.json",
      nativeSnapshotPath: "native.json", aiSnapshotPath: "ai.json", vegasSnapshotPath: "vegas.json",
      researchSnapshotPath: "research.json", sourceHash: "abc123",
    });
    const status = (await getSlateStatus(DATE, "main"))!;
    expect(status.status).toBe("PUBLISHED");
    expect(status.published_version).toBe(1);
    expect(status.published_pool_path).toBe("pool.json");
    expect(status.published_by).toBe(actor);
  });

  it("publishing twice creates two distinct, incrementing versions -- never overwrites history", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: "pool_v1.json", matchReportPath: null, ownershipPath: null, nativeSnapshotPath: null,
      aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: "hash1",
    });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: "pool_v2.json", matchReportPath: null, ownershipPath: null, nativeSnapshotPath: null,
      aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: "hash2",
    });

    const history = await listPublishHistory(DATE, "main");
    expect(history).toHaveLength(2);
    expect(new Set(history.map((h) => h.data_version))).toEqual(new Set([1, 2]));
    expect(history.find((h) => h.data_version === 1)!.pool_path).toBe("pool_v1.json");
    expect(history.find((h) => h.data_version === 2)!.pool_path).toBe("pool_v2.json");

    // The CURRENT pointer reflects only the latest publish.
    const version = (await getPublishedVersion(DATE, "main"))!;
    expect(version.dataVersion).toBe(2);
    expect(version.poolPath).toBe("pool_v2.json");
  });

  it("getPublishedVersion returns null for a slate that was never published", async () => {
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    expect(await getPublishedVersion(DATE, "main")).toBeNull();
  });

  it("listPublishedSlateIds only returns slates whose CURRENT status is PUBLISHED", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await upsertSlateStatus(DATE, "turbo", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: null, matchReportPath: null, ownershipPath: null, nativeSnapshotPath: null,
      aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: null,
    });
    expect(await listPublishedSlateIds(DATE)).toEqual(["main"]);
  });

  it("multiple published slates: Main, Turbo, and Night can all be published simultaneously, independently", async () => {
    const actor = await adminId();
    for (const slateId of ["main", "turbo", "night"]) {
      await upsertSlateStatus(DATE, slateId, { slateLabel: slateId, status: "READY" });
      await publishSlateRecord({
        slateDate: DATE, slateId, slateLabel: slateId, publishedBy: actor,
        poolPath: `${slateId}/pool.json`, matchReportPath: null, ownershipPath: null,
        nativeSnapshotPath: null, aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null,
        sourceHash: `${slateId}-hash`,
      });
    }

    expect(new Set(await listPublishedSlateIds(DATE))).toEqual(new Set(["main", "turbo", "night"]));
    // Each slate's own pinned version is independent -- no cross-slate leakage.
    expect((await getPublishedVersion(DATE, "main"))!.poolPath).toBe("main/pool.json");
    expect((await getPublishedVersion(DATE, "turbo"))!.poolPath).toBe("turbo/pool.json");
    expect((await getPublishedVersion(DATE, "night"))!.poolPath).toBe("night/pool.json");
  });

  it("atomic publish / failed refresh preserves the previous published version (V3 stays live while V4 build fails)", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: "pool_v1.json", matchReportPath: "report_v1.json", ownershipPath: "own_v1.json",
      nativeSnapshotPath: "native_v1.json", aiSnapshotPath: "ai_v1.json", vegasSnapshotPath: "vegas_v1.json",
      researchSnapshotPath: "research_v1.json", sourceHash: "hash-v1",
    });
    const v1 = (await getPublishedVersion(DATE, "main"))!;
    expect(v1.dataVersion).toBe(1);

    // Admin clicks Refresh Data: runSlatePipeline() (lib/slatePipeline.ts)
    // flips the CURRENT BUILD status to PROCESSING, then to ERROR when the
    // pipeline fails -- it never touches the published_* pointer columns.
    await upsertSlateStatus(DATE, "main", { status: "PROCESSING" });
    await upsertSlateStatus(DATE, "main", { status: "ERROR", poolPath: "pool_v2_attempt.json" });

    // The member-visible published version is completely untouched.
    const stillLive = (await getPublishedVersion(DATE, "main"))!;
    expect(stillLive.dataVersion).toBe(1);
    expect(stillLive.poolPath).toBe("pool_v1.json");
    expect(await listPublishedSlateIds(DATE)).toEqual(["main"]);

    // The raw build-status row shows the failed attempt for the admin board,
    // while displayStatus (effectiveDisplayStatus) still reads PUBLISHED.
    const raw = (await getSlateStatus(DATE, "main"))!;
    expect(raw.status).toBe("ERROR");
    expect(raw.pool_path).toBe("pool_v2_attempt.json"); // latest build attempt, admin-only view
    expect(effectiveDisplayStatus(raw)).toBe("PUBLISHED"); // member-facing status, unaffected
  });

  it("Last Updated consistency: every reader of the published version sees the identical timestamp", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: "pool.json", matchReportPath: null, ownershipPath: null, nativeSnapshotPath: null,
      aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: null,
    });

    // Command Center, the member Slate Manager page, Pitchers, Hitters, etc.
    // each call getPublishedVersion(date, slateId) independently -- they
    // must never derive "Last Updated" from anything else (like a fresh
    // artifact-file mtime), so two independent reads always agree exactly.
    const readAsCommandCenter = (await getPublishedVersion(DATE, "main"))!.publishedAt;
    const readAsSlateManagerPage = (await getPublishedVersion(DATE, "main"))!.publishedAt;
    expect(readAsCommandCenter).toBe(readAsSlateManagerPage);
    expect(readAsCommandCenter).toBe((await getSlateStatus(DATE, "main"))!.published_at);
  });
});

describe("unpublishSlate", () => {
  it("clears the published pointer and reverts status to READY, preserving history", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: "pool.json", matchReportPath: null, ownershipPath: null, nativeSnapshotPath: null,
      aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: null,
    });

    const ok = await unpublishSlate(DATE, "main", actor);
    expect(ok).toBe(true);

    const status = (await getSlateStatus(DATE, "main"))!;
    expect(status.status).toBe("READY");
    expect(status.published_version).toBeNull();
    expect(await getPublishedVersion(DATE, "main")).toBeNull();

    // History still has the PUBLISHED event -- never erased.
    const history = await listPublishHistory(DATE, "main");
    expect(history.some((h) => h.event === "PUBLISHED")).toBe(true);
    expect(history.some((h) => h.event === "UNPUBLISHED")).toBe(true);
  });

  it("returns false for a slate that isn't currently published", async () => {
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    expect(await unpublishSlate(DATE, "main", await adminId())).toBe(false);
  });
});

describe("archiveSlate", () => {
  it("archives a published slate, implicitly unpublishing it first", async () => {
    const actor = await adminId();
    await upsertSlateStatus(DATE, "main", { status: "READY" });
    await publishSlateRecord({
      slateDate: DATE, slateId: "main", slateLabel: "Main", publishedBy: actor,
      poolPath: null, matchReportPath: null, ownershipPath: null, nativeSnapshotPath: null,
      aiSnapshotPath: null, vegasSnapshotPath: null, researchSnapshotPath: null, sourceHash: null,
    });

    expect(await archiveSlate(DATE, "main", actor)).toBe(true);
    const status = (await getSlateStatus(DATE, "main"))!;
    expect(status.status).toBe("ARCHIVED");
    expect(await getPublishedVersion(DATE, "main")).toBeNull();

    const history = await listPublishHistory(DATE, "main");
    expect(history.some((h) => h.event === "ARCHIVED")).toBe(true);
  });

  it("returns false for an unknown slate", async () => {
    expect(await archiveSlate(DATE, "nope", await adminId())).toBe(false);
  });
});
