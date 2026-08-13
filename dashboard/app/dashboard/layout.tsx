import { GlobalSearch } from "@/components/GlobalSearch";
import { Sidebar } from "@/components/Sidebar";
import { getTodayChicagoDate } from "@/lib/currentDate";
import {
  latestKnownSlateDate,
  loadLatestBatterSnapshot,
  loadLatestLineupSet,
  loadLatestOwnershipSnapshot,
  loadLatestPitcherEvaluation,
  loadLatestPitcherSnapshot,
} from "@/lib/loaders";
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

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-bg-panel px-4 py-2.5">
          <div className="text-xs text-text-faint">
            Today: <span className="text-text-muted">{today}</span>
            {searchDate && searchDate !== today && <span className="ml-2 text-text-faint">(search index: {searchDate})</span>}
          </div>
          <GlobalSearch index={searchIndex} />
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto p-5">{children}</main>
      </div>
    </div>
  );
}
