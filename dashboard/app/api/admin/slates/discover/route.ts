import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSlateStatus } from "@/lib/db/slateStatus";
import { enqueueJob } from "@/lib/jobs/queue";
import { ensureSlateJobHandlersRegistered } from "@/lib/jobs/slateJobHandlers";
import { runOneQueuedJob } from "@/lib/jobs/worker";
import { listSlates } from "@/lib/optimizerWorkspace/poolCache";
import { isValidSlateDateString } from "@/lib/slateDate";

export const dynamic = "force-dynamic";

interface DiscoveredJob {
  slateId: string;
  slateName: string | null;
  jobId: string;
  startedAction: "slate_process_started" | "slate_refresh_started";
  completedAction: "slate_process_completed" | "slate_refresh_completed";
  failedAction: "slate_process_failed" | "slate_refresh_failed";
}

/** Admin-only "Refresh Today's Slates": the ONE-CLICK bulk counterpart
 * to the per-slate Process/Refresh buttons below it on /admin/slates.
 * Queries the currently configured DFS salary provider for every real
 * Classic slate on `date` (lib/optimizerWorkspace/poolCache.ts::listSlates
 * -> scripts/list_dfs_slates.py -- the SAME live discovery call
 * app/api/admin/slates/status/route.ts already makes on every status
 * poll, so this button never introduces a second, different notion of
 * "what slates exist today"), then enqueues the SAME PROCESS_SLATE/
 * REFRESH_SLATE job (lib/slatePipeline.ts::runSlatePipeline, via
 * lib/jobs/queue.ts) the individual Process Slate/Refresh Data buttons
 * already enqueue -- for EVERY discovered slate, not just one. Never
 * builds a second pipeline; this only loops the existing one.
 *
 * Never silently substitutes mock/synthetic data: if the provider isn't
 * connected (not_connected/unavailable/auth_failed/no_slate), this
 * returns 200 with providerStatus/providerReason set and zero jobs
 * started -- the UI shows that reason verbatim, never a fabricated
 * "0 slates today." A genuinely unexpected failure (a crash in
 * list_dfs_slates.py itself) still surfaces providerStatus:
 * "unavailable" with the real error in providerReason, not a 500 --
 * matches every other provider-status surface in this codebase (e.g.
 * scripts/fetch_dfs_slate.py's own "never crash the caller" contract).
 *
 * Jobs run SEQUENTIALLY (one full pipeline completes before the next
 * starts), deliberately NOT concurrently: two slate pipelines for the
 * SAME date write into SHARED date-scoped artifact paths
 * (dfs_input/<date>/... -- only ownership is slate-scoped, see
 * ownership/persistence.py) and lib/orchestrator/artifacts.ts's
 * fingerprint-based "did my write actually land" change-detection
 * assumes one writer at a time. Running two slates' pipelines at once
 * was confirmed (in this fix's own test) to make one pipeline's
 * fingerprint check see the OTHER pipeline's write and report a false
 * failure. All jobs are still enqueued immediately (fast, independent
 * DB rows) so the status board shows every slate as QUEUED right away;
 * only their actual execution is serialized. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  const { date } = (body as { date?: unknown }) ?? {};
  if (!isValidSlateDateString(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD, a valid calendar date) is required." }, { status: 400 });
  }

  const discovered = await listSlates(date);

  await recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_discover_started",
    targetType: "slate", targetId: date,
    metadata: {
      date, providerName: discovered.providerName, providerStatus: discovered.status,
      isMock: discovered.isMock, slatesDiscovered: discovered.slates.length,
    },
  });

  if (discovered.status !== "ready" || discovered.slates.length === 0) {
    return NextResponse.json({
      providerName: discovered.providerName,
      providerType: discovered.providerType,
      isMock: discovered.isMock,
      providerStatus: discovered.status,
      providerReason: discovered.reason,
      slatesDiscovered: [],
      jobs: [],
    });
  }

  ensureSlateJobHandlersRegistered();

  const results: Array<{ slateId: string; slateName: string | null; jobId: string | null; action: string }> = [];
  const toRun: DiscoveredJob[] = [];

  for (const s of discovered.slates) {
    const existing = await getSlateStatus(date, s.slateId);
    if (existing?.status === "PROCESSING") {
      results.push({ slateId: s.slateId, slateName: s.slateName, jobId: null, action: "skipped_already_processing" });
      continue;
    }
    // A slate this bulk action has already discovered once (a status
    // row exists) is a REFRESH, exactly the distinction a human clicking
    // the individual buttons would make -- "Process" is only for a
    // slate genuinely seen for the first time. Both enqueue the
    // identical job handler (lib/jobs/slateJobHandlers.ts ->
    // runSlatePipeline); this only changes the audit-trail label, per
    // app/api/admin/slates/process/route.ts and refresh/route.ts's own
    // docstrings on why the two actions exist separately.
    const isFirstRun = existing === null;
    const jobType = isFirstRun ? "PROCESS_SLATE" : "REFRESH_SLATE";
    const { job } = await enqueueJob({ jobType, slateDate: date, slateId: s.slateId, createdBy: admin.id, payload: { slateLabel: s.slateName } });
    await recordAuditLog({
      actorUserId: admin.id, actorLabel: admin.email, action: isFirstRun ? "slate_process_started" : "slate_refresh_started",
      targetType: "slate", targetId: `${date}:${s.slateId}`, metadata: { date, slateId: s.slateId, slateLabel: s.slateName, jobId: job.id },
    });
    toRun.push({
      slateId: s.slateId, slateName: s.slateName, jobId: job.id,
      startedAction: isFirstRun ? "slate_process_started" : "slate_refresh_started",
      completedAction: isFirstRun ? "slate_process_completed" : "slate_refresh_completed",
      failedAction: isFirstRun ? "slate_process_failed" : "slate_refresh_failed",
    });
    results.push({ slateId: s.slateId, slateName: s.slateName, jobId: job.id, action: isFirstRun ? "process" : "refresh" });
  }

  // Fire-and-forget: the HTTP response returns as soon as everything is
  // enqueued (see this route's own docstring for why this loop is
  // sequential, not Promise.all'd).
  void (async () => {
    for (const entry of toRun) {
      const result = await runOneQueuedJob(`inline-discover-${entry.jobId}`);
      const failed = result.status === "FAILED" || result.status === "NO_HANDLER";
      await recordAuditLog({
        actorUserId: admin.id, actorLabel: admin.email,
        action: failed ? entry.failedAction : entry.completedAction,
        targetType: "slate", targetId: `${date}:${entry.slateId}`,
        metadata: failed
          ? { date, slateId: entry.slateId, jobId: entry.jobId, error: result.job?.safe_error_message ?? null }
          : { date, slateId: entry.slateId, jobId: entry.jobId, status: (await getSlateStatus(date, entry.slateId))?.status ?? null },
      });
    }
  })();

  return NextResponse.json({
    providerName: discovered.providerName,
    providerType: discovered.providerType,
    isMock: discovered.isMock,
    providerStatus: discovered.status,
    providerReason: discovered.reason,
    slatesDiscovered: discovered.slates.map((s) => ({ slateId: s.slateId, slateName: s.slateName, gameCount: s.gameCount, playerCount: s.playerCount })),
    jobs: results,
  });
}
