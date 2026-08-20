import { PageHeader } from "@/components/ui/Header";
import { MissingDataState } from "@/components/MissingDataState";
import { ProjectionLabSummaryCards } from "@/components/projections/ProjectionLabSummaryCards";
import { ProjectionLabTable } from "@/components/projections/ProjectionLabTable";
import { loadActualDkPointsByPlayerId } from "@/lib/actualResults";
import { getAiProjectionByPlayerId } from "@/lib/aiProjections";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { getProjectionComparisonByPlayerId } from "@/lib/externalProjections";
import { getFantasyProsProjectionByPlayerId } from "@/lib/fantasyProsProjections";
import { loadLatestBatterSnapshot, loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { getNativeProjectionByPlayerId } from "@/lib/nativeProjections";
import { buildProjectionLabRows, buildProjectionLabSummary } from "@/lib/projectionLab";
import { effectiveGameIds, filterByGameIds, formatSlateLabel, resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

/** PROJECTION LAB (Milestone 27): the dedicated side-by-side comparison
 * of every projection source Big Money DFS carries for a player --
 * BlueCollar (if imported), Big Money Native, Big Money AI, and (once
 * postgame results exist) Actual DK -- so no column anywhere has to be
 * ambiguously labeled "Projection." Pure read/compose layer: every
 * value traces to an already-built, already-immutable snapshot; nothing
 * here recomputes a projection. Follows the SAME selected-slate scoping
 * every other Milestone 26 page uses -- Full Day shows the whole day's
 * pool, a selected slate shows only that slate's players. */
export default async function ProjectionLabPage(props: PageProps<"/dashboard/projections">) {
  const searchParams = await props.searchParams;
  const slateId = typeof searchParams.slate === "string" ? searchParams.slate : undefined;

  const date = getTodayChicagoDate();
  const slateCtx = await resolveSlateContext(date, slateId);
  const gameIds = effectiveGameIds(slateCtx);

  const pitcherSnapshot = loadLatestPitcherSnapshot(date).data;
  const batterSnapshot = loadLatestBatterSnapshot(date).data;
  const ownership = loadLatestOwnershipSnapshot(date, slateCtx.selected?.slateId ?? null).data;

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
  const dkPool = loadLatestDKPlayerPool(date, slateCtx.selected?.slateId ?? null).data;
  const pitcherRows = filterByGameIds(buildPitcherRows(pitcherSnapshot?.pitchers ?? [], ownership, dkPool), gameIds);
  const hitterRows = filterByGameIds(buildHitterRows(batterSnapshot?.hitters ?? [], ownership, dkPool), gameIds);

  const externalByPlayerId = getProjectionComparisonByPlayerId(date);
  const nativeByPlayerId = getNativeProjectionByPlayerId(date);
  const aiByPlayerId = getAiProjectionByPlayerId(date);
  const actualByPlayerId = loadActualDkPointsByPlayerId(date);
  // Milestone: FantasyPros -- the snapshot itself is date-scoped and
  // MLB-wide (FantasyPros doesn't know about DK slates); joining it here,
  // onto rows already filtered to this slate's games via filterByGameIds
  // above, is what actually satisfies "never show every FantasyPros
  // player" -- no slate-awareness needed inside fantasyProsProjections.ts.
  const fantasyProsByPlayerId = getFantasyProsProjectionByPlayerId(date);

  const rows = buildProjectionLabRows(
    [...pitcherRows, ...hitterRows],
    externalByPlayerId,
    nativeByPlayerId,
    aiByPlayerId,
    actualByPlayerId,
    fantasyProsByPlayerId,
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
