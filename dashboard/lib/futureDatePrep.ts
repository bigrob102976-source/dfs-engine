// MLB AUTOMATIC TOMORROW PREP -- makes tomorrow's real, already-
// prefetched DK Classic slate(s) fully optimizer-ready (research ->
// probable starters -> eligibility -> Native projections -> ownership)
// BEFORE Eastern midnight, whenever DraftKings has already published
// them, eliminating the empty-dashboard window that used to exist
// between rollover and the next automatic refresh cycle.
//
// ROOT CAUSE (see this milestone's own Phase 1 audit): tomorrow's real
// DK Classic slate(s) were ALREADY being fetched and promoted to
// canonical Postgres CURRENT every ~5-minute worker cycle
// (scripts/fetch_all_dfs_slates.py::prefetch_future_slates, Eastern-
// anchored, unchanged by this milestone) -- but
// scripts/refresh-research-and-eligibility.ts (research/identity/
// eligibility/Native-projection/ownership) was ONLY ever invoked for
// TODAY's own Eastern date (worker/run_dk_fetch_worker.ps1's `$Date`),
// never for tomorrow, regardless of whether tomorrow's canonical row
// already existed and was VALID. Confirmed live (2026-09-04, per that
// worker script's own comment): tomorrow's real, already-prefetched
// slate had 1,124 real players but 0 optimizer-eligible, 0 projections,
// 0 ownership -- not because anything was broken, but because nothing
// had ever asked this pipeline to run for that date.
//
// This module extends the EXISTING research-refresh pipeline
// (lib/canonicalRefresh.ts::runRefresh, reused completely unmodified --
// no new projection/ownership/eligibility logic) to ALSO prepare
// tomorrow, gated on:
//   1. DraftKings having ALREADY published at least one real, VALID
//      Classic slate for tomorrow (never fabricated/guessed) -- reusing
//      the canonical `slates` table the existing prefetch already wrote,
//      never a second DK fetch.
//   2. A cost-control freshness gate (default 25 minutes, MLB PREP
//      Phase 7's "20-30 minutes" guidance) so tomorrow's expensive
//      pipeline doesn't run on every 5-minute DK-fetch cycle -- reuses
//      the SAME "check the most recent real generated_at already in
//      Postgres" pattern refreshOwnershipForDate() already established,
//      no new state file or column needed.
//
// Never fetches DraftKings directly, never runs on a schedule of its
// own (called from the SAME worker cycle that already calls
// runRefresh() for today -- see scripts/prepare-next-day.ts), and never
// throws: every failure mode is reported in the returned result so a
// tomorrow-prep problem can never affect today's already-decided
// research-refresh outcome (MLB PREP Phase 10's explicit failure-
// isolation requirement).

import { getExecutor } from "./db/executor";
import { runRefresh, type RefreshSummary } from "./canonicalRefresh";

/** `date` is always an already-Eastern-anchored YYYY-MM-DD calendar-date
 * string (the same contract getTodayEasternDate() produces) -- this is
 * pure calendar arithmetic on that string, never a timezone conversion.
 * Parsing as UTC midnight and adding 24h is safe specifically because
 * the input has no time-of-day/timezone component to get wrong; DST
 * transitions (which only matter for real Eastern wall-clock instants)
 * don't apply to a bare calendar date. */
export function computeNextEasternDate(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export interface FutureDatePrepResult {
  date: string;
  sport: string;
  status: "NOT_YET_PUBLISHED" | "SKIPPED_RECENT" | "PREPARED" | "ERROR";
  slatesFound?: number;
  minutesSinceLastPrep?: number | null;
  summary?: RefreshSummary;
  error?: string;
}

/** The real gate + orchestration. `currentDate` is TODAY's own Eastern
 * date (the same value the worker already passes to runRefresh() for
 * today) -- tomorrow is derived from it, never independently computed,
 * so this can never drift out of sync with what "today" actually means
 * to the rest of this cycle. Never throws. */
export async function prepareFutureDateIfDue(
  currentDate: string, sport: string, throttleMinutes = 25,
): Promise<FutureDatePrepResult> {
  const nextDate = computeNextEasternDate(currentDate);
  try {
    const db = getExecutor();
    const slates = await db.all<{ internal_slate_id: string }>(
      "SELECT internal_slate_id FROM slates WHERE sport = ? AND slate_date = ? AND validation_state = 'VALID'",
      [sport, nextDate],
    );
    if (slates.length === 0) {
      // Real, honest "DraftKings hasn't published tomorrow yet" -- never
      // a failure, never fabricated. The next cycle whose DK-fetch
      // prefetch discovers a real slate for this date will make this
      // gate pass naturally.
      return { date: nextDate, sport, status: "NOT_YET_PUBLISHED", slatesFound: 0 };
    }

    const mostRecent = await db.get<{ latest: string | null }>(
      `SELECT MAX(generated_at) as latest FROM canonical_slate_player_projections WHERE internal_slate_id IN (${slates.map(() => "?").join(",")})`,
      slates.map((s) => s.internal_slate_id),
    );
    if (mostRecent?.latest) {
      const ageMinutes = (Date.now() - new Date(mostRecent.latest).getTime()) / 60000;
      if (ageMinutes < throttleMinutes) {
        return { date: nextDate, sport, status: "SKIPPED_RECENT", slatesFound: slates.length, minutesSinceLastPrep: Math.round(ageMinutes) };
      }
    }

    const summary = await runRefresh(nextDate, sport);
    return { date: nextDate, sport, status: "PREPARED", slatesFound: slates.length, summary };
  } catch (err) {
    // Belt-and-suspenders: runRefresh() itself never throws (every real
    // step is independently isolated), so reaching here means a bug in
    // THIS function's own gate logic, not a pipeline step's failure --
    // still reported, never allowed to propagate into the caller (which
    // may be the same process that just ran today's own refresh).
    return { date: nextDate, sport, status: "ERROR", error: err instanceof Error ? err.message : String(err) };
  }
}
