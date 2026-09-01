import { getExecutor } from "./executor";
import type { CanonicalSlateRow, IdentityReviewQueueRow } from "./types";

// M3J -- read-only queries backing the admin-only shadow ingestion
// monitor (app/admin/canonical-shadow/page.tsx,
// app/api/admin/canonical-shadow/route.ts). Reuses the EXISTING
// `slates` table (M3E's additive status columns) and
// `identity_review_queue` table -- no new tables, no write paths here.
// This module is read-only by design: it must never be used to
// implement any merge/edit/approve action (M3J explicitly defers
// identity review CONTROLS to a later milestone).

export interface ShadowSlateStatusView extends CanonicalSlateRow {
  ageSeconds: number | null;
}

/** All canonical slates, most recently attempted first. `sport` is an
 * optional filter (MLB-only today, but this is sport-neutral by
 * construction like every other canonical table). */
export async function listShadowSlateStatuses(sport?: string): Promise<ShadowSlateStatusView[]> {
  const db = getExecutor();
  const rows = sport
    ? await db.all<CanonicalSlateRow>("SELECT * FROM slates WHERE sport = ? ORDER BY last_attempt_at DESC NULLS LAST, updated_at DESC", [sport])
    : await db.all<CanonicalSlateRow>("SELECT * FROM slates ORDER BY last_attempt_at DESC NULLS LAST, updated_at DESC");

  const now = Date.now();
  return rows.map((row) => {
    const reference = row.last_attempt_at ?? row.updated_at;
    const referenceMs = reference ? new Date(reference).getTime() : NaN;
    return { ...row, ageSeconds: Number.isNaN(referenceMs) ? null : Math.max(0, Math.round((now - referenceMs) / 1000)) };
  });
}

/** Read-only identity review queue -- NO merge/edit/approve action
 * exists yet (M3J explicit scope boundary); this is visibility only. */
export async function listIdentityReviewQueue(status: "PENDING" | "RESOLVED" | "REJECTED" = "PENDING"): Promise<IdentityReviewQueueRow[]> {
  const db = getExecutor();
  return db.all<IdentityReviewQueueRow>("SELECT * FROM identity_review_queue WHERE status = ? ORDER BY created_at DESC", [status]);
}
