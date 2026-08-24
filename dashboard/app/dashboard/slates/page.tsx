import { RefreshStatusButton } from "@/components/RefreshStatusButton";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { getPublishedVersion } from "@/lib/db/slateStatus";
import { safeReadJson } from "@/lib/discovery";
import { resolveSlateContext } from "@/lib/slateContext";
import { resolveSlateDate } from "@/lib/slateDate";

export const dynamic = "force-dynamic";

interface DataStatusRow {
  label: string;
  ready: boolean;
}

// Milestone 30.1: the same eligibility breakdown dfs/eligibility.py
// computes and dfs/player_pool.py::build_match_report attaches to the
// published match report -- read-only here, never recomputed.
interface EligibilityCounts {
  starting_pitchers: number;
  confirmed_hitters: number;
  waiting_for_lineups: number;
  optimizer_eligible: number;
}

interface PlayerPoolSummary {
  startingPitchers: number;
  expectedPitcherSlots: number;
  confirmedHitters: number;
  expectedHitterSlots: number;
  waitingForLineups: number;
  optimizerEligible: number;
}

interface MemberSlateRow {
  slateId: string;
  slateName: string | null;
  lastUpdated: string | null;
  statuses: DataStatusRow[];
  playerPool: PlayerPoolSummary | null;
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Milestone 29: member-facing Slate Manager -- read-only. No CSV
 * upload, no file picker, no admin actions; everything an admin can DO
 * with a slate now lives exclusively on /admin/slates (Slate
 * Operations). resolveSlateContext() already filters `slates` to
 * PUBLISHED-only for a non-admin viewer (lib/memberSlateVisibility.ts),
 * so this page can never show a draft/processing/unpublished slate --
 * for each one it displays exactly what the spec asks for: Sport /
 * Slate / Last Updated / Data Status, sourced from the PUBLISHED
 * version's own pinned snapshot paths (lib/db/slateStatus.ts::
 * getPublishedVersion) so "Last Updated" and "READY" here always match
 * what a member is actually seeing elsewhere in the dashboard, not
 * whatever an admin's in-progress refresh happens to be building. */
export default async function SlateManagerPage(props: PageProps<"/dashboard/slates">) {
  const searchParams = await props.searchParams;
  const dateParam = typeof searchParams.date === "string" ? searchParams.date : undefined;
  const dateResolution = resolveSlateDate(dateParam);
  // Milestone 31.2C: an explicit ?date= (e.g. linked from /admin/slates
  // after DraftKings rolls its live lobby to the next calendar day)
  // lets a member view a slate for a date other than Chicago-today; an
  // invalid explicit value falls back to today rather than erroring a
  // whole-page navigation.
  const date = dateResolution.ok ? dateResolution.date : getTodayChicagoDate();
  const ctx = await resolveSlateContext(date);

  const rows: MemberSlateRow[] = await Promise.all(ctx.slates.map(async (s) => {
    const version = await getPublishedVersion(date, s.slateId);
    // Milestone 30.1: the same match report already pinned by publish
    // (version.matchReportPath) -- never a fresh/unpinned load, so this
    // widget always matches whatever slate a member is actually seeing.
    const matchReport = safeReadJson<{ dk_games_total?: number; eligibility?: EligibilityCounts }>(version?.matchReportPath ?? null);
    const eligibility = matchReport?.eligibility ?? null;
    const gamesTotal = matchReport?.dk_games_total ?? 0;
    const playerPool: PlayerPoolSummary | null = eligibility
      ? {
          startingPitchers: eligibility.starting_pitchers,
          expectedPitcherSlots: gamesTotal * 2, // 2 probable-starter slots per game
          confirmedHitters: eligibility.confirmed_hitters,
          expectedHitterSlots: gamesTotal * 18, // 9 starting hitters x 2 teams per game
          waitingForLineups: eligibility.waiting_for_lineups,
          optimizerEligible: eligibility.optimizer_eligible,
        }
      : null;
    return {
      slateId: s.slateId,
      slateName: s.slateName,
      lastUpdated: version?.publishedAt ?? null,
      statuses: [
        { label: "Lineups", ready: Boolean(version?.poolPath) },
        { label: "Vegas", ready: Boolean(version?.vegasSnapshotPath) },
        { label: "Native", ready: Boolean(version?.nativeSnapshotPath) },
        { label: "AI", ready: Boolean(version?.aiSnapshotPath) },
        { label: "Ownership", ready: Boolean(version?.ownershipPath) },
      ],
      playerPool,
    };
  }));

  return (
    <div>
      <PageHeader title="Slate Manager" description={`Published DraftKings slates for ${date}.`} actions={<RefreshStatusButton />} />

      {rows.length === 0 ? (
        <p className="p-4 text-xs text-text-faint">
          No slates have been published yet for {date} -- check back soon, or contact an admin.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((r) => (
            <div key={r.slateId} className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-faint">MLB</div>
              <div className="mb-3 text-sm font-semibold text-text">{r.slateName ?? r.slateId}</div>

              <div className="mb-3 text-[11px]">
                <span className="text-text-faint">Last Updated</span>{" "}
                <span className="text-text">{fmtDateTime(r.lastUpdated)}</span>
              </div>

              <dl className="mb-3 grid grid-cols-2 gap-y-1 text-[11px]">
                {r.statuses.map((st) => (
                  <div key={st.label} className="col-span-2 flex items-center justify-between">
                    <dt className="text-text-faint">{st.label}</dt>
                    <dd className={`font-semibold uppercase tracking-wide ${st.ready ? "text-green" : "text-text-faint"}`}>
                      {st.ready ? "READY" : "--"}
                    </dd>
                  </div>
                ))}
              </dl>

              {r.playerPool && (
                <div className="border-t border-border-subtle pt-2 text-[11px]">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Player Pool</div>
                  <div className="flex items-center justify-between">
                    <span className="text-text-faint">Starting Pitchers</span>
                    <span className="text-text">
                      {r.playerPool.startingPitchers}/{r.playerPool.expectedPitcherSlots} confirmed
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-text-faint">Starting Hitters</span>
                    <span className="text-text">
                      {r.playerPool.confirmedHitters}/{r.playerPool.expectedHitterSlots} confirmed
                    </span>
                  </div>
                  {r.playerPool.waitingForLineups > 0 && (
                    <div className="mt-1 text-yellow">{r.playerPool.waitingForLineups} hitters waiting for lineups to post</div>
                  )}
                  <div className="mt-1 flex items-center justify-between font-semibold">
                    <span className="text-text-faint">Optimizer Eligible</span>
                    <span className="text-green">{r.playerPool.optimizerEligible}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
