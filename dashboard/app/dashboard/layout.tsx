import { GlobalSearch } from "@/components/GlobalSearch";
import { Sidebar } from "@/components/Sidebar";
import { TopNavigation } from "@/components/TopNavigation";
import { getTodayChicagoDate } from "@/lib/currentDate";
import {
  latestKnownSlateDate,
  loadLatestBatterSnapshot,
  loadLatestLineupSet,
  loadLatestOwnershipSnapshot,
  loadLatestPitcherEvaluation,
  loadLatestPitcherSnapshot,
} from "@/lib/loaders";
import { getMockModeEnabled } from "@/lib/mockMode";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { buildSearchIndex } from "@/lib/search";

export const dynamic = "force-dynamic";

/** The header's "Today" label always reflects the true current
 * America/Chicago date -- never a stale artifact folder. Global search,
 * on the other hand, intentionally still indexes whatever the freshest
 * known artifacts are (which may be an earlier date if nothing has run
 * yet today), so search keeps working across the whole dashboard instead
 * of going empty every morning before the first refresh. */
export default async function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const today = getTodayChicagoDate();
  const searchDate = latestKnownSlateDate();
  const mockModeEnabled = await getMockModeEnabled();

  let searchIndex: ReturnType<typeof buildSearchIndex> = [];
  if (searchDate) {
    const pitcherSnapshot = loadLatestPitcherSnapshot(searchDate).data;
    const batterSnapshot = loadLatestBatterSnapshot(searchDate).data;
    const ownership = loadLatestOwnershipSnapshot(searchDate).data;
    const lineupSet = loadLatestLineupSet(searchDate).data;
    const pitcherEvaluation = loadLatestPitcherEvaluation(searchDate).data;

    const pitcherRows = buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, null);
    const hitterRows = buildHitterRows(batterSnapshot?.hitters ?? [], ownership, null);
    searchIndex = buildSearchIndex({ pitcherRows, hitterRows, lineupSet, pitcherEvaluation });
  }

  const slateLabel = searchDate && searchDate !== today ? `Today · ${today} (search: ${searchDate})` : `Today · ${today}`;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-bg">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {mockModeEnabled && (
          <div
            role="status"
            className="flex shrink-0 items-center justify-center gap-1.5 bg-yellow px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-black"
          >
            <span aria-hidden="true">⚠</span> DEV MODE -- Mock DFS data is active. No real DraftKings salaries.
          </div>
        )}
        <TopNavigation slateLabel={slateLabel} search={<GlobalSearch index={searchIndex} />} />
        <main className="min-w-0 flex-1 overflow-y-auto p-5">{children}</main>
      </div>
    </div>
  );
}
