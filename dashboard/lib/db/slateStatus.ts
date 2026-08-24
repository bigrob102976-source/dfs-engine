import crypto from "node:crypto";

import { getExecutor } from "./executor";
import type { SqlExecutor } from "./sqlExecutor";
import type { PublishedSlateVersion, SlateLifecycleStatus, SlatePublishHistoryRow, SlateStatusRow } from "./types";

/** Milestone 29: the admin-owned "what state is this slate in" record --
 * one row per (slate_date, slate_id), upserted freely as processing
 * proceeds. This is NOT the publish history (see slate_publish_history
 * below) -- it's a fast, always-current pointer a member-facing loader
 * or the admin Slate Operations board can read in one query. */

/** The status a MEMBER (or the admin board's headline column) should
 * see: PUBLISHED whenever a version is currently live, regardless of
 * whatever a concurrent Process/Refresh's raw `status` column says
 * (that raw column tracks the CURRENT BUILD ATTEMPT, not visibility --
 * see listPublishedSlateIds's docstring). Admin views that want to show
 * "a refresh is in progress" too should read `row.status` directly
 * alongside this, not instead of it. */
export function effectiveDisplayStatus(row: SlateStatusRow): SlateLifecycleStatus {
  return row.published_version != null ? "PUBLISHED" : row.status;
}

interface UpsertPatch {
  slateLabel?: string | null;
  status?: SlateLifecycleStatus;
  poolPath?: string | null;
  matchReportPath?: string | null;
  ownershipPath?: string | null;
  nativeSnapshotPath?: string | null;
  aiSnapshotPath?: string | null;
  vegasSnapshotPath?: string | null;
  researchSnapshotPath?: string | null;
  sourceHash?: string | null;
  sourceProvenance?: string | null;
  validationJson?: string | null;
  changeReportJson?: string | null;
  lastProcessedAt?: string | null;
  lastRefreshedAt?: string | null;
}

async function getSlateStatusVia(db: SqlExecutor, slateDate: string, slateId: string): Promise<SlateStatusRow | null> {
  const row = await db.get<Record<string, unknown>>("SELECT * FROM slate_status WHERE slate_date = ? AND slate_id = ?", [
    slateDate,
    slateId,
  ]);
  return (row as unknown as SlateStatusRow) ?? null;
}

export async function getSlateStatus(slateDate: string, slateId: string): Promise<SlateStatusRow | null> {
  return getSlateStatusVia(getExecutor(), slateDate, slateId);
}

export async function listSlateStatuses(slateDate: string): Promise<SlateStatusRow[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>("SELECT * FROM slate_status WHERE slate_date = ? ORDER BY slate_id", [slateDate]);
  return rows as unknown as SlateStatusRow[];
}

/** Insert-or-update by (slate_date, slate_id). Only fields present in
 * `patch` are changed -- callers pass exactly what a given pipeline step
 * (process, refresh, error) actually knows, never invent the rest. */
export async function upsertSlateStatus(slateDate: string, slateId: string, patch: UpsertPatch): Promise<SlateStatusRow> {
  const db = getExecutor();
  const existing = await getSlateStatusVia(db, slateDate, slateId);
  const now = new Date().toISOString();

  if (!existing) {
    const id = crypto.randomUUID();
    await db.run(
      `INSERT INTO slate_status (
        id, slate_date, slate_id, slate_label, status,
        pool_path, match_report_path, ownership_path, native_snapshot_path, ai_snapshot_path,
        vegas_snapshot_path, research_snapshot_path, source_hash, source_provenance, validation_json,
        change_report_json, last_processed_at, last_refreshed_at, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        id, slateDate, slateId, patch.slateLabel ?? null, patch.status ?? "DRAFT",
        patch.poolPath ?? null, patch.matchReportPath ?? null, patch.ownershipPath ?? null,
        patch.nativeSnapshotPath ?? null, patch.aiSnapshotPath ?? null,
        patch.vegasSnapshotPath ?? null, patch.researchSnapshotPath ?? null,
        patch.sourceHash ?? null, patch.sourceProvenance ?? null, patch.validationJson ?? null,
        patch.changeReportJson ?? null, patch.lastProcessedAt ?? null, patch.lastRefreshedAt ?? null, now, now,
      ],
    );
    return (await getSlateStatusVia(db, slateDate, slateId))!;
  }

  const next = {
    slate_label: patch.slateLabel !== undefined ? patch.slateLabel : existing.slate_label,
    status: patch.status ?? existing.status,
    pool_path: patch.poolPath !== undefined ? patch.poolPath : existing.pool_path,
    match_report_path: patch.matchReportPath !== undefined ? patch.matchReportPath : existing.match_report_path,
    ownership_path: patch.ownershipPath !== undefined ? patch.ownershipPath : existing.ownership_path,
    native_snapshot_path: patch.nativeSnapshotPath !== undefined ? patch.nativeSnapshotPath : existing.native_snapshot_path,
    ai_snapshot_path: patch.aiSnapshotPath !== undefined ? patch.aiSnapshotPath : existing.ai_snapshot_path,
    vegas_snapshot_path: patch.vegasSnapshotPath !== undefined ? patch.vegasSnapshotPath : existing.vegas_snapshot_path,
    research_snapshot_path: patch.researchSnapshotPath !== undefined ? patch.researchSnapshotPath : existing.research_snapshot_path,
    source_hash: patch.sourceHash !== undefined ? patch.sourceHash : existing.source_hash,
    source_provenance: patch.sourceProvenance !== undefined ? patch.sourceProvenance : existing.source_provenance,
    validation_json: patch.validationJson !== undefined ? patch.validationJson : existing.validation_json,
    change_report_json: patch.changeReportJson !== undefined ? patch.changeReportJson : existing.change_report_json,
    last_processed_at: patch.lastProcessedAt !== undefined ? patch.lastProcessedAt : existing.last_processed_at,
    last_refreshed_at: patch.lastRefreshedAt !== undefined ? patch.lastRefreshedAt : existing.last_refreshed_at,
  };

  await db.run(
    `UPDATE slate_status SET
      slate_label = ?, status = ?, pool_path = ?, match_report_path = ?, ownership_path = ?,
      native_snapshot_path = ?, ai_snapshot_path = ?, vegas_snapshot_path = ?, research_snapshot_path = ?,
      source_hash = ?, source_provenance = ?, validation_json = ?, change_report_json = ?,
      last_processed_at = ?, last_refreshed_at = ?, updated_at = ?
     WHERE slate_date = ? AND slate_id = ?`,
    [
      next.slate_label, next.status, next.pool_path, next.match_report_path, next.ownership_path,
      next.native_snapshot_path, next.ai_snapshot_path, next.vegas_snapshot_path, next.research_snapshot_path,
      next.source_hash, next.source_provenance, next.validation_json, next.change_report_json,
      next.last_processed_at, next.last_refreshed_at, now,
      slateDate, slateId,
    ],
  );
  return (await getSlateStatusVia(db, slateDate, slateId))!;
}

/** Milestone 29 atomic-member-view guarantee: gated ONLY on
 * `published_version IS NOT NULL`, never on the mutable `status` column.
 * `status` also tracks the CURRENT build attempt (upsertSlateStatus()
 * flips it to PROCESSING/READY/PARTIAL/ERROR on every Process/Refresh,
 * including a refresh of an already-published slate) -- if this query
 * gated on status = 'PUBLISHED' instead, a slate would incorrectly
 * disappear from members the instant an admin clicked Refresh, even
 * though its published_* pointer columns (and therefore the actual
 * artifacts members read) are completely untouched until a NEW Publish. */
export async function listPublishedSlateIds(slateDate: string): Promise<string[]> {
  const db = getExecutor();
  const rows = await db.all<{ slate_id: string }>("SELECT slate_id FROM slate_status WHERE slate_date = ? AND published_version IS NOT NULL", [
    slateDate,
  ]);
  return rows.map((r) => r.slate_id);
}

/** The pinned snapshot paths a member-facing (atomic) loader should read
 * -- null whenever the slate isn't currently published. See
 * listPublishedSlateIds's docstring immediately above for why this is
 * gated on published_version alone, not on `status`. */
export async function getPublishedVersion(slateDate: string, slateId: string): Promise<PublishedSlateVersion | null> {
  const row = await getSlateStatus(slateDate, slateId);
  if (!row || row.published_version == null) return null;
  return {
    slateDate: row.slate_date,
    slateId: row.slate_id,
    dataVersion: row.published_version,
    publishedAt: row.published_at ?? "",
    poolPath: row.published_pool_path,
    matchReportPath: row.published_match_report_path,
    ownershipPath: row.published_ownership_path,
    nativeSnapshotPath: row.published_native_snapshot_path,
    aiSnapshotPath: row.published_ai_snapshot_path,
    vegasSnapshotPath: row.published_vegas_snapshot_path,
    researchSnapshotPath: row.published_research_snapshot_path,
    sourceHash: row.published_source_hash,
  };
}

async function nextDataVersionVia(db: SqlExecutor, slateDate: string, slateId: string): Promise<number> {
  const row = await db.get<{ maxVersion: number | null }>(
    "SELECT MAX(data_version) as maxVersion FROM slate_publish_history WHERE slate_date = ? AND slate_id = ?",
    [slateDate, slateId],
  );
  return (row?.maxVersion ?? 0) + 1;
}

/** Low-level DB mutation for a publish event -- assumes readiness has
 * ALREADY been validated by the caller (lib/slatePublishReadiness.ts);
 * this module has no opinion on what makes a slate publishable, only how
 * to record that it was published. Inserts an append-only history row
 * (never overwritten) AND updates slate_status's "currently live"
 * pointer fields inside ONE transaction -- both writes commit or roll
 * back together on both backends (Milestone 33.1: previously best-effort
 * back-to-back statements with no real atomicity guarantee). Computing
 * the next data_version is inside the same transaction too, so two
 * concurrent publishes for the same slate can never compute the same
 * version number. */
export async function publishSlateRecord(args: {
  slateDate: string;
  slateId: string;
  slateLabel: string | null;
  publishedBy: string;
  poolPath: string | null;
  matchReportPath: string | null;
  ownershipPath: string | null;
  nativeSnapshotPath: string | null;
  aiSnapshotPath: string | null;
  vegasSnapshotPath: string | null;
  researchSnapshotPath: string | null;
  sourceHash: string | null;
}): Promise<SlatePublishHistoryRow> {
  const db = getExecutor();
  const publishedAt = new Date().toISOString();
  const id = crypto.randomUUID();

  const dataVersion = await db.transaction(async (tx) => {
    const version = await nextDataVersionVia(tx, args.slateDate, args.slateId);

    await tx.run(
      `INSERT INTO slate_publish_history (
        id, slate_date, slate_id, slate_label, data_version, event, published_at, published_by, source_hash,
        pool_path, match_report_path, ownership_path, native_snapshot_path, ai_snapshot_path,
        vegas_snapshot_path, research_snapshot_path
      ) VALUES (?, ?, ?, ?, ?, 'PUBLISHED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        id, args.slateDate, args.slateId, args.slateLabel, version, publishedAt, args.publishedBy, args.sourceHash,
        args.poolPath, args.matchReportPath, args.ownershipPath, args.nativeSnapshotPath, args.aiSnapshotPath,
        args.vegasSnapshotPath, args.researchSnapshotPath,
      ],
    );

    await tx.run(
      `UPDATE slate_status SET
        status = 'PUBLISHED', published_version = ?, published_at = ?, published_by = ?,
        published_pool_path = ?, published_match_report_path = ?, published_ownership_path = ?,
        published_native_snapshot_path = ?, published_ai_snapshot_path = ?,
        published_vegas_snapshot_path = ?, published_research_snapshot_path = ?, published_source_hash = ?,
        updated_at = ?
       WHERE slate_date = ? AND slate_id = ?`,
      [
        version, publishedAt, args.publishedBy,
        args.poolPath, args.matchReportPath, args.ownershipPath,
        args.nativeSnapshotPath, args.aiSnapshotPath, args.vegasSnapshotPath, args.researchSnapshotPath, args.sourceHash,
        publishedAt,
        args.slateDate, args.slateId,
      ],
    );

    return version;
  });

  return {
    id, slate_date: args.slateDate, slate_id: args.slateId, slate_label: args.slateLabel, data_version: dataVersion,
    event: "PUBLISHED", published_at: publishedAt, published_by: args.publishedBy, source_hash: args.sourceHash,
    pool_path: args.poolPath, match_report_path: args.matchReportPath, ownership_path: args.ownershipPath,
    native_snapshot_path: args.nativeSnapshotPath, ai_snapshot_path: args.aiSnapshotPath,
    vegas_snapshot_path: args.vegasSnapshotPath, research_snapshot_path: args.researchSnapshotPath,
  };
}

/** Un-publishes a slate: clears slate_status's "currently live" pointer
 * (so getPublishedVersion() returns null and member-facing loaders stop
 * serving it) and drops the lifecycle status back to READY -- the
 * underlying processed artifacts are untouched, only visibility changes.
 * Records an UNPUBLISHED row in the history log (append-only, same as
 * every other event here) so "this was live from T1 to T2" is
 * reconstructable later. Both writes run in one transaction. Returns
 * false if the slate wasn't published. */
export async function unpublishSlate(slateDate: string, slateId: string, actorUserId: string): Promise<boolean> {
  const db = getExecutor();
  const existing = await getSlateStatusVia(db, slateDate, slateId);
  if (!existing || existing.status !== "PUBLISHED") return false;

  const publishedAt = new Date().toISOString();
  await db.transaction(async (tx) => {
    await tx.run(
      `INSERT INTO slate_publish_history (
        id, slate_date, slate_id, slate_label, data_version, event, published_at, published_by, source_hash,
        pool_path, match_report_path, ownership_path, native_snapshot_path, ai_snapshot_path,
        vegas_snapshot_path, research_snapshot_path
      ) VALUES (?, ?, ?, ?, ?, 'UNPUBLISHED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        crypto.randomUUID(), slateDate, slateId, existing.slate_label, existing.published_version ?? 0, publishedAt,
        actorUserId, existing.published_source_hash,
        existing.published_pool_path, existing.published_match_report_path, existing.published_ownership_path,
        existing.published_native_snapshot_path, existing.published_ai_snapshot_path,
        existing.published_vegas_snapshot_path, existing.published_research_snapshot_path,
      ],
    );

    await tx.run(
      `UPDATE slate_status SET
        status = 'READY', published_version = NULL, published_at = NULL, published_by = NULL,
        published_pool_path = NULL, published_match_report_path = NULL, published_ownership_path = NULL,
        published_native_snapshot_path = NULL, published_ai_snapshot_path = NULL,
        published_vegas_snapshot_path = NULL, published_research_snapshot_path = NULL, published_source_hash = NULL,
        updated_at = ?
       WHERE slate_date = ? AND slate_id = ?`,
      [publishedAt, slateDate, slateId],
    );
  });

  return true;
}

/** Archives a slate (terminal-ish, keeps it out of normal admin/member
 * views without deleting anything). If it was published, this ALSO
 * un-publishes it first (a member must never keep seeing an archived
 * slate) and records both events -- as its own, separately-atomic
 * transaction (a crash between the two leaves the slate correctly
 * unpublished-but-not-yet-archived, a safe and recoverable state, not a
 * corrupted one; re-running Archive finishes the job). */
export async function archiveSlate(slateDate: string, slateId: string, actorUserId: string): Promise<boolean> {
  const db = getExecutor();
  const existing = await getSlateStatusVia(db, slateDate, slateId);
  if (!existing) return false;

  if (existing.status === "PUBLISHED") {
    await unpublishSlate(slateDate, slateId, actorUserId);
  }

  const now = new Date().toISOString();
  await db.transaction(async (tx) => {
    await tx.run(
      `INSERT INTO slate_publish_history (
        id, slate_date, slate_id, slate_label, data_version, event, published_at, published_by, source_hash,
        pool_path, match_report_path, ownership_path, native_snapshot_path, ai_snapshot_path,
        vegas_snapshot_path, research_snapshot_path
      ) VALUES (?, ?, ?, ?, ?, 'ARCHIVED', ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)`,
      [crypto.randomUUID(), slateDate, slateId, existing.slate_label, existing.published_version ?? 0, now, actorUserId],
    );

    await tx.run("UPDATE slate_status SET status = 'ARCHIVED', updated_at = ? WHERE slate_date = ? AND slate_id = ?", [
      now,
      slateDate,
      slateId,
    ]);
  });
  return true;
}

export async function listPublishHistory(slateDate: string, slateId: string): Promise<SlatePublishHistoryRow[]> {
  const db = getExecutor();
  // `id` (a UUID) is a portable tiebreaker for events recorded in the
  // same millisecond -- see lib/db/auditLog.ts's identical reasoning;
  // publish history only ever needs a stable tiebreak, not true
  // insertion order, so no `seq`-style schema change is needed here.
  const rows = await db.all<Record<string, unknown>>(
    "SELECT * FROM slate_publish_history WHERE slate_date = ? AND slate_id = ? ORDER BY published_at DESC, id DESC",
    [slateDate, slateId],
  );
  return rows as unknown as SlatePublishHistoryRow[];
}
