import { SlateManagerClient } from "@/components/slates/SlateManagerClient";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { loadLatestDKPlayerPool, loadLatestDkMatchReport, loadLatestOwnershipSnapshot } from "@/lib/loaders";
import { resolveSlateContext } from "@/lib/slateContext";
import type { SlateManagerRow } from "@/components/slates/types";

export const dynamic = "force-dynamic";

/** Milestone 26: Slate Manager -- every DraftKings slate discovered for
 * today (Main/Turbo/Night/...), each one's build status (READY/PARTIAL/
 * MISSING, from whether a slate-scoped player pool and ownership
 * snapshot exist -- see ownership/persistence.py's slate-scoping fix),
 * and the actions to Open/Replace/Refresh/Remove it. The one place a
 * user manages the day's slates instead of navigating the Optimizer's
 * dropdown one slate at a time. */
export default async function SlateManagerPage() {
  const date = getTodayChicagoDate();
  const ctx = await resolveSlateContext(date);

  const rows: SlateManagerRow[] = ctx.slates.map((s) => {
    const pool = loadLatestDKPlayerPool(date, s.slateId).data;
    const ownership = loadLatestOwnershipSnapshot(date, s.slateId).data;
    const status: SlateManagerRow["status"] = pool && ownership ? "READY" : pool || ownership ? "PARTIAL" : "MISSING";
    const matchReport = loadLatestDkMatchReport(date, s.slateId).data;
    const sourceProvenance = (matchReport?.source_provenance as string | undefined) ?? null;
    const realism = matchReport?.source_realism as { blocked?: boolean } | undefined;
    return {
      slateId: s.slateId,
      slateName: s.slateName,
      gameCount: s.gameCount,
      playerCount: pool?.player_count ?? s.playerCount,
      startTime: s.startTime,
      status,
      sourceProvenance,
      realismBlocked: realism?.blocked ?? false,
    };
  });

  return (
    <div>
      <PageHeader title="Slate Manager" description={`Today's DraftKings slates for ${date}.`} />
      <SlateManagerClient
        date={date}
        rows={rows}
        providerName={ctx.providerName}
        isMock={ctx.isMock}
        providerStatus={ctx.status}
      />
    </div>
  );
}
