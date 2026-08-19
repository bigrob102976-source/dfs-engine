import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { listAuditLog } from "@/lib/db/auditLog";
import { effectiveDisplayStatus, listSlateStatuses } from "@/lib/db/slateStatus";
import { listJobsForSlate } from "@/lib/jobs/queue";
import { listSlates } from "@/lib/optimizerWorkspace/poolCache";
import { evaluatePublishReadiness } from "@/lib/slatePublishReadiness";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
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
  if (!DATE_RE.test(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD) query param is required." }, { status: 400 });
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
    };
  });

  const recentOperations = listAuditLog({ limit: 50 }).filter((entry) => SLATE_AUDIT_ACTIONS.has(entry.action));

  return NextResponse.json({
    date, providerName: discovered.providerName, isMock: discovered.isMock, slates, recentOperations,
  });
}
