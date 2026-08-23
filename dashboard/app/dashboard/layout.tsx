import { redirect } from "next/navigation";

import { GlobalSearch } from "@/components/GlobalSearch";
import { GlobalSlateSelector } from "@/components/layout/GlobalSlateSelector";
import { GlobalSlateSync } from "@/components/layout/GlobalSlateSync";
import { Sidebar } from "@/components/Sidebar";
import { TopNavigation } from "@/components/TopNavigation";
import { hasProductAccess } from "@/lib/auth/betaAccess";
import { requireAuth } from "@/lib/auth/guards";
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
import { resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

/** The header's "Today" label always reflects the true current
 * America/Chicago date -- never a stale artifact folder. Global search,
 * on the other hand, intentionally still indexes whatever the freshest
 * known artifacts are (which may be an earlier date if nothing has run
 * yet today), so search keeps working across the whole dashboard instead
 * of going empty every morning before the first refresh. */
export default async function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  // The single choke point every /dashboard/* page passes through --
  // redirects to /login when there's no valid session. Role/entitlement
  // -specific checks happen per-feature, not here (this dashboard is
  // MLB-only and every current feature is seeded PRODUCTION/entitled by
  // subscription; a future per-feature gate would call
  // isFeatureVisibleToUser() from a specific page, not this shared layout).
  const user = await requireAuth();
  // Milestone 30: PRIVATE_BETA=true gate -- ADMIN always passes;
  // everyone else needs an explicit beta grant (lib/auth/betaAccess.ts).
  // A no-op when PRIVATE_BETA isn't set, so local dev/tests are
  // unaffected unless an operator explicitly opts in.
  if (!hasProductAccess(user)) {
    redirect("/beta-access-required");
  }
  const today = getTodayChicagoDate();
  const searchDate = latestKnownSlateDate();
  const mockModeEnabled = await getMockModeEnabled();
  const slateCtx = await resolveSlateContext(today);

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
      <GlobalSlateSync />
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
        <TopNavigation
          slateLabel={slateLabel}
          slateSelector={<GlobalSlateSelector slates={slateCtx.slates} />}
          search={<GlobalSearch index={searchIndex} />}
          user={{ email: user.email, isAdmin: user.role === "ADMIN" }}
        />
        <main className="min-w-0 flex-1 overflow-y-auto p-5">{children}</main>
      </div>
    </div>
  );
}
