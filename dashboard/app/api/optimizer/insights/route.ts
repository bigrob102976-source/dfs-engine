import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { bestValuePitcher } from "@/lib/commandCenter";
import { getTodayEasternDate } from "@/lib/currentDate";
import { loadLatestBatterSnapshot, loadLatestDKPlayerPool, loadLatestOwnershipSnapshot, loadLatestPitcherSnapshot } from "@/lib/loaders";
import { buildHitterRows, buildPitcherRows } from "@/lib/normalize";
import { isValidSlateId } from "@/lib/optimizerWorkspace/validateSlateId";
import { effectiveGameIds, filterByGameIds, resolveSlateContext } from "@/lib/slateContext";
import { resolveSlateDate } from "@/lib/slateDate";
import { buildStackCandidates, buildStackSummaries, rankStackCandidatesByScore, rankStackCandidatesByValue } from "@/lib/stacks";

export const dynamic = "force-dynamic";

/** MLB DASHBOARD INTELLIGENCE (Phase 9): server-side Top Stacks / Best
 * Value Pitcher / Best Value Stack for a given date + slate, reusing the
 * EXACT same real data/loaders/ranking functions app/dashboard/page.tsx
 * already uses (lib/loaders.ts, lib/normalize.ts, lib/stacks.ts,
 * lib/commandCenter.ts) -- no second computation, no fabricated data.
 * `source: "legacy"` names the pipeline these numbers came from (the
 * real production path every member sees today); this stays honest and
 * self-describing if a canonical-backed variant is ever added later. */
export async function GET(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const url = new URL(request.url);
  const slateId = url.searchParams.get("slate");
  if (slateId !== null && !isValidSlateId(slateId)) {
    return NextResponse.json({ error: "\"slate\" must be a non-empty string." }, { status: 400 });
  }
  const dateResolution = resolveSlateDate(url.searchParams.get("date") ?? getTodayEasternDate());
  if (!dateResolution.ok) {
    return NextResponse.json({ error: dateResolution.error }, { status: 400 });
  }
  const date = dateResolution.date;

  const slateCtx = await resolveSlateContext(date, slateId, { autoSelectSoleSlate: true });
  const gameIds = effectiveGameIds(slateCtx);
  const selectedSlateId = slateCtx.selected?.slateId ?? null;

  const [pitcherSnapshotLoaded, batterSnapshotLoaded, ownershipLoaded, dkPoolLoaded] = await Promise.all([
    loadLatestPitcherSnapshot(date),
    loadLatestBatterSnapshot(date),
    loadLatestOwnershipSnapshot(date, selectedSlateId),
    loadLatestDKPlayerPool(date, selectedSlateId),
  ]);

  const pitcherRows = filterByGameIds(buildPitcherRows(pitcherSnapshotLoaded.data?.pitchers ?? [], ownershipLoaded.data, dkPoolLoaded.data), gameIds);
  const hitterRows = filterByGameIds(buildHitterRows(batterSnapshotLoaded.data?.hitters ?? [], ownershipLoaded.data, dkPoolLoaded.data), gameIds);
  const stacks = buildStackSummaries(hitterRows, ownershipLoaded.data?.team_popularity ?? {});
  const stackCandidates = buildStackCandidates(stacks);

  return NextResponse.json({
    bestValuePitcher: bestValuePitcher(pitcherRows),
    topStacks: rankStackCandidatesByScore(stackCandidates).slice(0, 5),
    bestValueStack: rankStackCandidatesByValue(stackCandidates)[0] ?? null,
    generatedAt: new Date().toISOString(),
    slateId: selectedSlateId,
    source: "legacy",
  });
}
