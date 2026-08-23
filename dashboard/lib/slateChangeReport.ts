// M32.7: "After Refresh Data, show what changed." Captures a small,
// cheap BEFORE/AFTER snapshot of already-persisted state around one
// runSlatePipeline() call and diffs them -- never a new computation of
// eligibility/projections itself, only a read of what those steps
// already produced. captureSlateState() is pure I/O (reads the same
// artifacts every other loader in this file reads); diffSlateState() is
// pure and independently testable.

import { getAiProjectionByPlayerId } from "./aiProjections";
import { loadLatestBlueCollarSnapshot } from "./blueCollarProjections";
import { loadLatestEnvironmentReport } from "./gameEnvironment";
import { loadLatestDKPlayerPool, loadLatestDkMatchReport } from "./loaders";
import { getMlProjectionByPlayerId } from "./mlProjections";
import { getNativeProjectionByPlayerId } from "./nativeProjections";

export interface SlateStateSnapshot {
  teamsAwaitingLineups: string[];
  confirmedHitters: number;
  optimizerEligible: number;
  startingPitcherIdByTeam: Record<string, string>;
  nativePlayerCount: number;
  aiPlayerCount: number;
  mlPlayerCount: number;
  environmentGeneratedAt: string | null;
  blueCollarUpdated: string | null;
}

export function captureSlateState(date: string, slateId: string): SlateStateSnapshot {
  const matchReport = loadLatestDkMatchReport(date, slateId).data;
  const eligibility = (matchReport?.eligibility as Record<string, number> | undefined) ?? {};
  const pool = loadLatestDKPlayerPool(date, slateId).data;

  const startingPitcherIdByTeam: Record<string, string> = {};
  for (const p of pool?.players ?? []) {
    if (p.player_type === "pitcher" && p.eligibility_status === "STARTING_PITCHER" && p.mlb_player_id) {
      startingPitcherIdByTeam[p.team] = p.mlb_player_id;
    }
  }

  return {
    teamsAwaitingLineups: (matchReport?.teams_awaiting_lineups as string[] | undefined) ?? [],
    confirmedHitters: eligibility.confirmed_hitters ?? 0,
    optimizerEligible: eligibility.optimizer_eligible ?? 0,
    startingPitcherIdByTeam,
    nativePlayerCount: getNativeProjectionByPlayerId(date).size,
    aiPlayerCount: getAiProjectionByPlayerId(date).size,
    mlPlayerCount: getMlProjectionByPlayerId(date).size,
    environmentGeneratedAt: loadLatestEnvironmentReport(date)?.generated_at ?? null,
    blueCollarUpdated: loadLatestBlueCollarSnapshot(date, slateId)?.bluecollar_updated ?? null,
  };
}

export interface SlateChangeReport {
  lineupsPosted: number;
  hittersBecameEligible: number;
  starterChanged: number;
  nativeGenerated: number;
  aiGenerated: number;
  mlGenerated: number;
  stacksBecameReady: number;
  unchanged: string[];
}

function countStarterChanges(before: Record<string, string>, after: Record<string, string>): number {
  let changed = 0;
  for (const [team, afterId] of Object.entries(after)) {
    const beforeId = before[team];
    if (beforeId && beforeId !== afterId) changed += 1;
  }
  return changed;
}

/** Pure diff -- no I/O. `unchanged` lists exactly the signals this
 * refresh's own snapshots prove didn't move (never a guess: Vegas/
 * Weather are read from the SAME environment report's own generated_at
 * timestamp; BlueCollar from its own `updated` field). */
export function diffSlateState(before: SlateStateSnapshot, after: SlateStateSnapshot): SlateChangeReport {
  const teamsBefore = new Set(before.teamsAwaitingLineups);
  const teamsAfter = new Set(after.teamsAwaitingLineups);
  const lineupsPosted = [...teamsBefore].filter((t) => !teamsAfter.has(t)).length;

  const unchanged: string[] = [];
  if (before.environmentGeneratedAt !== null && before.environmentGeneratedAt === after.environmentGeneratedAt) {
    unchanged.push("Vegas", "Weather");
  }
  if (before.blueCollarUpdated !== null && before.blueCollarUpdated === after.blueCollarUpdated) {
    unchanged.push("BlueCollar");
  }

  return {
    lineupsPosted,
    hittersBecameEligible: Math.max(0, after.confirmedHitters - before.confirmedHitters),
    starterChanged: countStarterChanges(before.startingPitcherIdByTeam, after.startingPitcherIdByTeam),
    nativeGenerated: Math.max(0, after.nativePlayerCount - before.nativePlayerCount),
    aiGenerated: Math.max(0, after.aiPlayerCount - before.aiPlayerCount),
    mlGenerated: Math.max(0, after.mlPlayerCount - before.mlPlayerCount),
    // A team becomes stack-ready the instant its lineup posts (see
    // lib/stacks.ts::buildStackSummaries -- CONFIRMED iff >=1 STARTING_HITTER
    // row exists), so this coincides with lineupsPosted by definition,
    // not a coincidental approximation.
    stacksBecameReady: lineupsPosted,
    unchanged,
  };
}
