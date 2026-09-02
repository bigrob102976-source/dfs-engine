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

// M4H -- prefetch/freshness are deliberately SEPARATE concepts (per this
// milestone's explicit instruction not to confuse them): FRESH/STALE/
// ABSENT (ageSeconds-based, already above) describes how RECENTLY a
// slate was successfully attempted; PrefetchState below describes WHICH
// calendar day (America/New_York -- the same canonical slateDate
// contract acquisition itself uses, see canonical/slate_date.py and
// scripts/fetch_all_dfs_slates.py's own _eastern_date_offset) a slate
// row belongs to relative to today. A slate can be simultaneously
// FUTURE_PREFETCHED and, say, STALE-by-age -- both are reported, never
// collapsed into one flag.
export type PrefetchState = "PAST" | "TODAY_CURRENT" | "FUTURE_PREFETCHED";

const EASTERN_DATE_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
});

/** Returns the America/New_York calendar date `days` days from right
 * now, as YYYY-MM-DD. Anchored at noon UTC before shifting so the
 * result is correct across a DST transition (noon UTC is always
 * comfortably inside the same Eastern calendar day, never near either
 * boundary). Display/observability use only -- never wired into any
 * write/decision path (those stay in canonical/slate_date.py on the
 * Python side); dashboard/lib/currentDate.ts's Chicago-anchored
 * customer-facing "today" is intentionally untouched by this. */
export function easternDateOffset(days: number): string {
  const parts = EASTERN_DATE_FORMATTER.formatToParts(new Date());
  const get = (type: string) => Number(parts.find((p) => p.type === type)!.value);
  const noonUtcToday = Date.UTC(get("year"), get("month") - 1, get("day"), 12, 0, 0);
  return EASTERN_DATE_FORMATTER.format(new Date(noonUtcToday + days * 24 * 60 * 60 * 1000));
}

function classifyPrefetchState(slateDate: string, todayEastern: string): PrefetchState {
  if (slateDate === todayEastern) return "TODAY_CURRENT";
  if (slateDate > todayEastern) return "FUTURE_PREFETCHED";
  return "PAST";
}

// M7K -- read-only eligibility observability, extending this SAME
// read-only admin monitor with the M6/M7 eligibility state (never an
// edit control -- this module's own M3J scope boundary above still
// applies). "unconfirmedCount" covers both LINEUP_UNCONFIRMED (real
// research package, lineup just not posted yet -- M7D) and NULL
// (eligibility never computed for this player at all) -- both are
// honest "not yet known" states, never conflated with UNMATCHED (a
// real, negative identity/game-matching result).
export interface EligibilitySummary {
  totalPlayers: number;
  eligibleCount: number;
  unconfirmedCount: number;
  unmatchedCount: number;
  lastComputedAt: string | null;
}

interface EligibilitySummaryRow {
  internal_slate_id: string;
  total_players: number;
  eligible_count: number;
  unconfirmed_count: number;
  unmatched_count: number;
  last_computed_at: string | null;
}

/** One aggregate GROUP BY query for every slate at once -- never N+1,
 * mirroring this module's own read-only, no-new-table design. */
export async function getEligibilitySummariesBySlate(): Promise<Map<string, EligibilitySummary>> {
  const db = getExecutor();
  const rows = await db.all<EligibilitySummaryRow>(
    `SELECT
       internal_slate_id,
       COUNT(*) as total_players,
       SUM(CASE WHEN optimizer_eligible = 1 THEN 1 ELSE 0 END) as eligible_count,
       SUM(CASE WHEN eligibility_status IS NULL OR eligibility_status = 'LINEUP_UNCONFIRMED' THEN 1 ELSE 0 END) as unconfirmed_count,
       SUM(CASE WHEN eligibility_status = 'UNMATCHED' THEN 1 ELSE 0 END) as unmatched_count,
       MAX(eligibility_computed_at) as last_computed_at
     FROM slate_players
     GROUP BY internal_slate_id`,
  );
  const bySlate = new Map<string, EligibilitySummary>();
  for (const row of rows) {
    bySlate.set(row.internal_slate_id, {
      totalPlayers: Number(row.total_players),
      eligibleCount: Number(row.eligible_count),
      unconfirmedCount: Number(row.unconfirmed_count),
      unmatchedCount: Number(row.unmatched_count),
      lastComputedAt: row.last_computed_at,
    });
  }
  return bySlate;
}

export interface ShadowSlateStatusView extends CanonicalSlateRow {
  ageSeconds: number | null;
  prefetchState: PrefetchState;
  eligibility: EligibilitySummary | null;
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
  const todayEastern = easternDateOffset(0);
  const eligibilityBySlate = await getEligibilitySummariesBySlate();
  return rows.map((row) => {
    const reference = row.last_attempt_at ?? row.updated_at;
    const referenceMs = reference ? new Date(reference).getTime() : NaN;
    return {
      ...row,
      ageSeconds: Number.isNaN(referenceMs) ? null : Math.max(0, Math.round((now - referenceMs) / 1000)),
      prefetchState: classifyPrefetchState(row.slate_date, todayEastern),
      eligibility: eligibilityBySlate.get(row.internal_slate_id) ?? null,
    };
  });
}

export interface TomorrowPrefetchSummary {
  /** America/New_York calendar date this summary describes. */
  date: string;
  /** M4H/M4L: NOT_YET_PUBLISHED is an honest absence, never a failure --
   * see scripts/fetch_all_dfs_slates.py::prefetch_future_slates. */
  status: "FUTURE_PREFETCHED" | "NOT_YET_PUBLISHED";
  slates: ShadowSlateStatusView[];
}

/** M4H -- admin-monitor summary of tomorrow's (America/New_York)
 * prefetch state. Reuses listShadowSlateStatuses() (never a second,
 * divergent query) -- the absence of any row for tomorrow's date is
 * NOT_YET_PUBLISHED, exactly mirroring the worker's own honest-absence
 * reporting; it is never inferred from anything customer-facing. */
export async function getTomorrowPrefetchSummary(sport?: string): Promise<TomorrowPrefetchSummary> {
  const tomorrow = easternDateOffset(1);
  const all = await listShadowSlateStatuses(sport);
  const slates = all.filter((s) => s.slate_date === tomorrow);
  return { date: tomorrow, status: slates.length > 0 ? "FUTURE_PREFETCHED" : "NOT_YET_PUBLISHED", slates };
}

/** Read-only identity review queue -- NO merge/edit/approve action
 * exists yet (M3J explicit scope boundary); this is visibility only. */
export async function listIdentityReviewQueue(status: "PENDING" | "RESOLVED" | "REJECTED" = "PENDING"): Promise<IdentityReviewQueueRow[]> {
  const db = getExecutor();
  return db.all<IdentityReviewQueueRow>("SELECT * FROM identity_review_queue WHERE status = ? ORDER BY created_at DESC", [status]);
}
