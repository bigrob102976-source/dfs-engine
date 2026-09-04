import { PageHeader } from "@/components/ui/Header";
import { MissingDataState } from "@/components/MissingDataState";
import { ProjectionLabSummaryCards } from "@/components/projections/ProjectionLabSummaryCards";
import { ProjectionLabTable } from "@/components/projections/ProjectionLabTable";
import { loadActualDkPointsByPlayerId } from "@/lib/actualResults";
import { getAiProjectionByPlayerId } from "@/lib/aiProjections";
import { getBlueCollarProjectionByPlayerId } from "@/lib/blueCollarProjections";
import { getTodayEasternDate } from "@/lib/currentDate";
import { getFantasyProsProjectionByPlayerId } from "@/lib/fantasyProsProjections";
import { loadLatestBatterSnapshot, loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { getMlProjectionByPlayerId } from "@/lib/mlProjections";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { getNativeProjectionByPlayerId } from "@/lib/nativeProjections";
import { buildProjectionLabRows, buildProjectionLabSummary } from "@/lib/projectionLab";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

/** PROJECTION LAB (Milestone 27): the dedicated side-by-side comparison
 * of every projection source Big Money DFS carries for a player --
 * BlueCollar (live, slate-matched -- see lib/blueCollarProjections.ts),
 * Big Money Native, Big Money AI, Big Money ML, and (once postgame
 * results exist) Actual DK -- so no column anywhere has to be
 * ambiguously labeled "Projection." Pure read/compose layer: every
 * value traces to an already-built, already-immutable snapshot; nothing
 * here recomputes a projection. Follows the SAME selected-slate scoping
 * every other Milestone 26 page uses -- Full Day shows the whole day's
 * pool, a selected slate shows only that slate's players. */
export default async function ProjectionLabPage(props: PageProps<"/dashboard/projections">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayEasternDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const gameIds = effectiveGameIds(slateCtx);

  const [pitcherSnapshotLoaded, batterSnapshotLoaded, ownershipLoaded] = await Promise.all([
    loadLatestPitcherSnapshot(date),
    loadLatestBatterSnapshot(date),
    loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null),
  ]);
  const pitcherSnapshot = pitcherSnapshotLoaded.data;
  const batterSnapshot = batterSnapshotLoaded.data;
  const ownership = ownershipLoaded.data;

  if (!pitcherSnapshot && !batterSnapshot) {
    return (
      <div>
        <PageHeader title="Projection Lab" description="Compare projection sources, model adjustments, and actual performance." />
        <MissingDataState
          title="No research available yet for today's slate"
          description="Generate today's pitcher and hitter research to populate the Projection Lab."
          primaryActionLabel="Refresh Required Data"
          targetSteps={["pitchers", "batters"]}
        />
      </div>
    );
  }

  // Milestone 27.2: without the real DK pool, a real DK-salaried player
  // whose team's lineup hasn't posted yet never gets a row here either.
  const [
    dkPoolLoaded,
    // BlueCollar Live Projection Integration: slate-scoped (never
    // date-only) -- see lib/blueCollarProjections.ts's module docstring
    // for why this is a separate pipeline from the older, generic
    // "External"/"Adjusted" comparison-baseline mechanism.
    blueCollarByPlayerId,
    nativeByPlayerId,
    aiByPlayerId,
    actualByPlayerId,
    // Milestone: FantasyPros -- the snapshot itself is date-scoped and
    // MLB-wide (FantasyPros doesn't know about DK slates); joining it here,
    // onto rows already filtered to this slate's games via filterByGameIds
    // above, is what actually satisfies "never show every FantasyPros
    // player" -- no slate-awareness needed inside fantasyProsProjections.ts.
    fantasyProsByPlayerId,
    // Milestone 32.2B: Big Money ML -- SHADOW, comparison-only (pitchers,
    // starters only). Same date-scoped join discipline as FantasyPros above.
    mlByPlayerId,
  ] = await Promise.all([
    loadLatestDKPlayerPool(date, slateCtx.selected?.slateId ?? null),
    getBlueCollarProjectionByPlayerId(date, slateCtx.selected?.slateId ?? null),
    getNativeProjectionByPlayerId(date),
    getAiProjectionByPlayerId(date),
    loadActualDkPointsByPlayerId(date),
    getFantasyProsProjectionByPlayerId(date),
    getMlProjectionByPlayerId(date),
  ]);
  const dkPool = dkPoolLoaded.data;
  const pitcherRows = filterByGameIds(buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, dkPool), gameIds);
  const hitterRows = filterByGameIds(buildHitterRows(batterSnapshot?.hitters ?? [], ownership, dkPool), gameIds);

  const rows = buildProjectionLabRows(
    [...pitcherRows, ...hitterRows],
    blueCollarByPlayerId,
    nativeByPlayerId,
    aiByPlayerId,
    actualByPlayerId,
    fantasyProsByPlayerId,
    mlByPlayerId,
  );
  const summary = buildProjectionLabSummary(rows);
  const slateDescription = slateCtx.selected ? ` -- ${formatSlateLabel(slateCtx.selected)}` : " -- Full Day";

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Projection Lab"
        description={`Compare projection sources, model adjustments, and actual performance.${slateDescription}`}
      />
      <ProjectionLabSummaryCards summary={summary} />
      <ProjectionLabTable rows={rows} />
    </div>
  );
}
