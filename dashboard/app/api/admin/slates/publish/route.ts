import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSlateStatus, publishSlateRecord } from "@/lib/db/slateStatus";
import { evaluatePublishReadiness } from "@/lib/slatePublishReadiness";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Admin-only Publish: the ONLY way a slate becomes visible to members
 * (lib/slateContext.ts::resolveSlateContext filters every member-facing
 * slate list to lib/db/slateStatus.ts::listPublishedSlateIds). Refuses
 * unless every REQUIRED readiness check passes (trusted source
 * provenance, valid game resolution, player pool built, pool identity
 * integrity passed, Native projections available) -- Vegas/AI/Ownership
 * may be missing and are reported, never silently pretended ready. Pins
 * the CURRENT build's exact snapshot paths into an append-only publish-
 * history row (never overwritten) and slate_status's "currently live"
 * pointer, in one atomic step from the caller's perspective -- a member
 * reading mid-request either sees the old version's full data or the
 * new version's full data, never a mix (see lib/db/slateStatus.ts's
 * module docstring). */
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
  const { date, slateId } = (body as { date?: unknown; slateId?: unknown }) ?? {};
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "`date` (YYYY-MM-DD) is required." }, { status: 400 });
  }
  if (typeof slateId !== "string" || !slateId) {
    return NextResponse.json({ error: "`slateId` is required." }, { status: 400 });
  }

  const readiness = evaluatePublishReadiness(date, slateId);
  if (!readiness.ok) {
    return NextResponse.json(
      { error: "This slate is not ready to publish.", readiness },
      { status: 422 },
    );
  }

  const existing = getSlateStatus(date, slateId);
  const history = publishSlateRecord({
    slateDate: date, slateId, slateLabel: existing?.slate_label ?? null, publishedBy: admin.id,
    poolPath: existing?.pool_path ?? null, matchReportPath: existing?.match_report_path ?? null,
    ownershipPath: existing?.ownership_path ?? null, nativeSnapshotPath: existing?.native_snapshot_path ?? null,
    aiSnapshotPath: existing?.ai_snapshot_path ?? null, vegasSnapshotPath: existing?.vegas_snapshot_path ?? null,
    researchSnapshotPath: existing?.research_snapshot_path ?? null, sourceHash: existing?.source_hash ?? null,
  });

  recordAuditLog({
    actorUserId: admin.id, actorLabel: admin.email, action: "slate_published",
    targetType: "slate", targetId: `${date}:${slateId}`,
    metadata: { date, slateId, dataVersion: history.data_version, sourceHash: history.source_hash },
  });

  return NextResponse.json({ status: "published", dataVersion: history.data_version, publishedAt: history.published_at });
}
