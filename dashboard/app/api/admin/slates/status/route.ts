import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { computeBlueCollarCoverage, loadLatestBlueCollarSnapshot, type BlueCollarCoverage } from "@/lib/blueCollarProjections";
import { listAuditLog } from "@/lib/db/auditLog";
import { effectiveDisplayStatus, listSlateStatuses } from "@/lib/db/slateStatus";
import { listJobsForSlate } from "@/lib/jobs/queue";
import { loadLatestDkMatchReport, loadLatestDKPlayerPool } from "@/lib/loaders";
import { listSlates } from "@/lib/optimizerWorkspace/poolCache";
import { isValidSlateDateString } from "@/lib/slateDate";
import type { SlateChangeReport } from "@/lib/slateChangeReport";
import { evaluatePublishReadiness } from "@/lib/slatePublishReadiness";

// Milestone 30.1: the eligibility breakdown dfs/eligibility.py computes
// and dfs/player_pool.py::build_match_report attaches to the saved match
// report's "eligibility" key -- read-only here, never recomputed.
interface EligibilityCounts {
  raw_dk_players: number;
  starting_pitchers: number;
  relief_pitchers: number;
  confirmed_hitters: number;
  bench_hitters: number;
  waiting_for_lineups: number;
  scratched: number;
  unmatched: number;
  ambiguous: number;
  optimizer_eligible: number;
}

// Canonical MLB Player Identity Foundation: PLAYER IDENTITY is
// deliberately reported separately from `eligibility` above -- identity
// (does this DK row resolve to a real mlb_player_id) and eligibility
// (is this player optimizer-buildable today) are two different
// questions. Sourced from the SAME match report dfs/player_pool.py's
// build_match_report already writes (matched_to_mlb/unmatched_count/
// ambiguous_count/dk_entries) -- nothing new computed here, just a
// second read of fields that already existed.
interface IdentityCounts {
  dk_entries: number;
  resolved: number;
  ambiguous: number;
  unmatched: number;
}

export const dynamic = "force-dynamic";

const SLATE_AUDIT_ACTIONS = new Set([
  "slate_process_started", "slate_process_completed", "slate_process_failed",
  "slate_refresh_started", "slate_refresh_completed", "slate_refresh_failed",
  "slate_published", "slate_unpublished", "slate_archived",
]);

/** Admin-only status board data: every slate the configured provider
 * currently discovers for `date` (ADMIN sees every lifecycle state, per
 * this milestone's explicit "Admin may view all states"), each merged
 * with its lib/db/slateStatus.ts row (if a process has ever run for it)
 * and a fresh publish-readiness evaluation. Also returns recent slate-
 * related operations from the existing admin_audit_log
 * (lib/db/auditLog.ts) -- reused, not duplicated. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const { searchParams } = new URL(request.url);
  const date = searchParams.get("date") ?? "";
  if (!isValidSlateDateString(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD, a valid calendar date) query param is required." }, { status: 400 });
  }

  const discovered = await listSlates(date);
  const statusRows = listSlateStatuses(date);
  const statusById = new Map(statusRows.map((r) => [r.slate_id, r]));

  const slates = discovered.slates.map((s) => {
    const statusRow = statusById.get(s.slateId) ?? null;
    const readiness = evaluatePublishReadiness(date, s.slateId);
    // Milestone 30: the most recent QUEUED/RUNNING job for this slate, if
    // any -- lets the Slate Operations UI show a live progress bar/step
    // while a Process/Refresh job is in flight, backed by the durable
    // `jobs` table (lib/jobs/queue.ts) rather than only the coarse
    // PROCESSING/READY/PARTIAL/ERROR status column.
    const activeJob = listJobsForSlate(date, s.slateId).find((j) => j.status === "QUEUED" || j.status === "RUNNING") ?? null;
    const matchReport = loadLatestDkMatchReport(date, s.slateId).data;
    const eligibility = (matchReport?.eligibility as EligibilityCounts | undefined) ?? null;
    const identity: IdentityCounts | null = matchReport
      ? {
          dk_entries: (matchReport.dk_entries as number) ?? 0,
          resolved: (matchReport.matched_to_mlb as number) ?? 0,
          ambiguous: (matchReport.ambiguous_count as number) ?? 0,
          unmatched: (matchReport.unmatched_count as number) ?? 0,
        }
      : null;
    // M32.7: BlueCollar's own funnel (returned/usable/identity-resolved/
    // eligible/optimizer-ready), read cheaply -- the already-persisted
    // pool + BlueCollar snapshot, never poolCache.ts's heavier loadPool()
    // (which can invoke Python if nothing is cached yet -- unsafe to call
    // from a route a status-board poll hits every few seconds).
    const pool = loadLatestDKPlayerPool(date, s.slateId).data;
    const blueCollarSnapshot = loadLatestBlueCollarSnapshot(date, s.slateId);
    const optimizerIds = new Set(
      (pool?.players ?? []).filter((p) => p.optimizer_eligible && p.mlb_player_id).map((p) => p.mlb_player_id as string),
    );
    const blueCollarCoverage: BlueCollarCoverage = computeBlueCollarCoverage(blueCollarSnapshot, optimizerIds);
    // M32.7: the most recent Process/Refresh run's change report, if any
    // (see lib/slateChangeReport.ts) -- null for a slate that has never
    // completed a run since this column was added.
    let changeReport: SlateChangeReport | null = null;
    if (statusRow?.change_report_json) {
      try {
        changeReport = JSON.parse(statusRow.change_report_json) as SlateChangeReport;
      } catch {
        changeReport = null;
      }
    }
    return {
      slateId: s.slateId,
      slateName: s.slateName,
      gameCount: s.gameCount,
      playerCount: s.playerCount,
      buildStatus: statusRow?.status ?? "DRAFT",
      displayStatus: statusRow ? effectiveDisplayStatus(statusRow) : "DRAFT",
      sourceProvenance: statusRow?.source_provenance ?? null,
      sourceHash: statusRow?.source_hash ?? null,
      lastProcessedAt: statusRow?.last_processed_at ?? null,
      lastRefreshedAt: statusRow?.last_refreshed_at ?? null,
      publishedVersion: statusRow?.published_version ?? null,
      publishedAt: statusRow?.published_at ?? null,
      readiness,
      activeJob: activeJob ? { id: activeJob.id, jobType: activeJob.job_type, status: activeJob.status, progress: activeJob.progress, currentStep: activeJob.current_step } : null,
      eligibility,
      identity,
      blueCollarCoverage,
      changeReport,
    };
  });

  const recentOperations = listAuditLog({ limit: 50 }).filter((entry) => SLATE_AUDIT_ACTIONS.has(entry.action));

  return NextResponse.json({
    date, providerName: discovered.providerName, isMock: discovered.isMock, slates, recentOperations,
  });
}
