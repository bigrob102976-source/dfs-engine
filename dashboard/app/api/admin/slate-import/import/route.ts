import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { findAutomaticSlateCollision, importDkCsvToCanonical } from "@/lib/adminCsvImport";
import { recordAuditLog } from "@/lib/db/auditLog";
import { enqueueJob } from "@/lib/jobs/queue";
import { ensureSlateJobHandlersRegistered } from "@/lib/jobs/slateJobHandlers";
import { runOneQueuedJob } from "@/lib/jobs/worker";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10MB -- a real DK Classic export is a few hundred KB even at hundreds of players.

/** BREAK-GLASS ADMIN CSV UPLOAD, Phases 3/5/6/7/10: the "Import Slate"
 * step. ADMIN only (rule #2/#7/#10 -- requireAdminApi() gives MEMBER a
 * 403 and unauthenticated a redirect/401, this project's existing
 * convention). Never auto-imports on file selection -- this route only
 * runs when the admin explicitly submits the Import form (Phase 2's
 * explicit rule), and re-validates the file server-side regardless of
 * what the client's earlier /validate call reported (defense in depth --
 * never trusts a hidden button or stale client state, rule #10). */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ ok: false, reason: "Request must be multipart/form-data." }, { status: 400 });
  }

  const file = form.get("file");
  const date = form.get("date");
  const slateLabel = form.get("slateLabel");
  const confirmSeparateSlate = form.get("confirmSeparateSlate") === "true";

  if (!(file instanceof File)) {
    return NextResponse.json({ ok: false, reason: "Missing CSV file." }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return NextResponse.json({ ok: false, reason: "Only .csv files are supported." }, { status: 400 });
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ ok: false, reason: `File is too large (${file.size} bytes) -- a real DraftKings CSV export never exceeds ${MAX_UPLOAD_BYTES} bytes.` }, { status: 413 });
  }
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ ok: false, reason: "Invalid slate date." }, { status: 400 });
  }
  if (typeof slateLabel !== "string" || !slateLabel.trim()) {
    return NextResponse.json({ ok: false, reason: "A slate label (Main, Turbo, Night, ...) is required." }, { status: 400 });
  }
  const label = slateLabel.trim();

  // Phase 6: never silently collide with a real, already-serving
  // automatic slate for this date. Admin-CSV rows can never literally
  // overwrite one (distinct `provider` value in the canonical unique
  // identity), but the admin must still see and explicitly acknowledge
  // that a live automatic slate already exists before adding a second
  // one for the date.
  const collisions = await findAutomaticSlateCollision(date, "MLB");
  if (collisions.length > 0 && !confirmSeparateSlate) {
    return NextResponse.json(
      { ok: false, requiresConfirmation: true, reason: "A live automatic slate already exists for this date.", collisions },
      { status: 409 },
    );
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const result = await importDkCsvToCanonical(bytes, date, label, file.name);

  if (!result.ok) {
    await recordAuditLog({
      actorUserId: admin.id, actorLabel: admin.email, action: "admin_csv_import_failed",
      targetType: "slate", targetId: date, metadata: { date, slateLabel: label, filename: file.name, reason: result.reason },
    });
    return NextResponse.json(result, { status: 422 });
  }

  await recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "admin_csv_imported",
    targetType: "slate", targetId: result.internalSlateId ?? date,
    metadata: {
      date, slateLabel: label, filename: file.name, providerSlateId: result.providerSlateId,
      playerCount: result.playerCount, sourceProvenance: result.sourceProvenance,
      hadAutomaticSlateCollision: collisions.length > 0,
    },
  });

  // Phase 7: kick off the same real research/identity/eligibility/
  // Native-projection/ownership refresh the automatic path runs, via the
  // SAME durable job queue Process/Refresh Slate already uses -- never a
  // bare fire-and-forget promise (see app/api/admin/slates/process/route.ts's
  // own precedent for this exact pattern).
  ensureSlateJobHandlersRegistered();
  const { job } = await enqueueJob({ jobType: "REFRESH_CANONICAL_DATE", slateDate: date, slateId: null, createdBy: admin.id, payload: { sport: "MLB" } });

  runOneQueuedJob(`inline-${job.id}`).then(async (jobResult) => {
    const failed = jobResult.status === "FAILED" || jobResult.status === "NO_HANDLER";
    await recordAuditLog({
      actorUserId: admin.id, actorLabel: admin.email,
      action: failed ? "admin_csv_downstream_refresh_failed" : "admin_csv_downstream_refresh_completed",
      targetType: "slate", targetId: result.internalSlateId ?? date,
      metadata: failed ? { date, jobId: job.id, error: jobResult.job?.safe_error_message ?? null } : { date, jobId: job.id },
    });
  });

  return NextResponse.json({ ...result, downstreamRefreshJobId: job.id }, { status: 200 });
}
