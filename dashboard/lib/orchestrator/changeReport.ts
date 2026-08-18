import { safeReadJson } from "../discovery";
import type { BatterSnapshot, DKPlayerPool, LineupSet, OwnershipSnapshot } from "../types";
import type { ChangeReport, ExposureChange, RunState } from "./types";

function emptyChangeReport(): ChangeReport {
  return {
    previousRunId: null,
    previousFinishedAt: null,
    newPostedLineupGames: null,
    scratches: [],
    starterChanges: [],
    salaryChangedCount: null,
    projectionChangedCount: null,
    ownershipChangedCount: null,
    exposureChanges: [],
    notes: [],
  };
}

function stepPath(run: RunState, id: string): string | null {
  return run.steps.find((s) => s.id === id)?.artifactPath ?? null;
}

function exposurePercentByName(lineupSet: LineupSet | null): Map<string, number> {
  const pct = new Map<string, number>();
  const total = lineupSet?.lineups?.length ?? 0;
  if (!total) return pct;
  const counts = new Map<string, number>();
  for (const lineup of lineupSet!.lineups) {
    for (const assignment of lineup.assignments ?? []) {
      counts.set(assignment.name, (counts.get(assignment.name) ?? 0) + 1);
    }
  }
  for (const [name, count] of counts) pct.set(name, Math.round((100 * count) / total));
  return pct;
}

/** Pure diff between the previous completed run and this one -- reads
 * only the immutable JSON artifacts each run already recorded the path
 * to (never re-derives or invents anything, and never mutates either
 * run). Returns an all-null/empty report with an explanatory note when
 * there's nothing valid to compare against (first refresh of the day,
 * or a previous run for a different date). */
export function buildChangeReport(previous: RunState | null, current: RunState): ChangeReport {
  const report = emptyChangeReport();

  if (!previous || previous.status !== "completed" || !previous.summary) {
    report.notes.push("No prior completed refresh today to compare against.");
    return report;
  }
  if (previous.slateDate !== current.slateDate) {
    report.notes.push(`Previous completed refresh was for ${previous.slateDate}, not today (${current.slateDate}) -- nothing to compare.`);
    return report;
  }

  // Milestone 27.3: DraftKings player IDs are only unique within a single
  // slate's own CSV export (confirmed in M26) -- the per-player diffs
  // below fall back to raw dk_player_id as a join key for any player
  // without an mlb_player_id yet, so comparing across two DIFFERENT
  // slates on the same date (e.g. the user switched from "Main" to a
  // "Turbo" slate between refreshes) could silently attribute a salary/
  // projection/ownership change to the wrong unmatched player. Bail out
  // exactly like the slateDate guard above rather than risk that.
  const previousSlateId = previous.summary?.selectedSlateId ?? null;
  const currentSlateId = current.summary?.selectedSlateId ?? null;
  if (previousSlateId !== currentSlateId) {
    report.notes.push(
      `Previous completed refresh was for a different slate (${previousSlateId ?? "unknown"} vs ${currentSlateId ?? "unknown"}) -- nothing to compare.`,
    );
    return report;
  }

  report.previousRunId = previous.runId;
  report.previousFinishedAt = previous.finishedAt;

  const prevBatters = safeReadJson<BatterSnapshot>(stepPath(previous, "batters"));
  const currBatters = safeReadJson<BatterSnapshot>(stepPath(current, "batters"));
  if (prevBatters && currBatters) {
    const prevStarters = new Map((prevBatters.hitters ?? []).map((h) => [h.player_id, h]));
    const currStarters = new Map((currBatters.hitters ?? []).map((h) => [h.player_id, h]));
    const prevGamesPosted = new Set((prevBatters.hitters ?? []).map((h) => h.game_id));
    const currGamesPosted = new Set((currBatters.hitters ?? []).map((h) => h.game_id));
    report.newPostedLineupGames = [...currGamesPosted].filter((g) => !prevGamesPosted.has(g)).length;

    for (const [playerId, player] of prevStarters) {
      if (!currStarters.has(playerId)) report.scratches.push(player.name);
    }
    for (const [playerId, player] of currStarters) {
      const prevPlayer = prevStarters.get(playerId);
      if (prevPlayer && prevPlayer.batting_order !== player.batting_order) {
        report.starterChanges.push(`${player.name}: batting order ${prevPlayer.batting_order ?? "?"} -> ${player.batting_order ?? "?"}`);
      }
    }
  } else {
    report.notes.push("Batter snapshot missing for one of the two runs -- cannot compare posted lineups.");
  }

  const prevPool = safeReadJson<DKPlayerPool>(stepPath(previous, "playerPool"));
  const currPool = safeReadJson<DKPlayerPool>(stepPath(current, "playerPool"));
  if (prevPool && currPool) {
    const prevByPlayer = new Map((prevPool.players ?? []).map((p) => [p.mlb_player_id ?? p.dk_player_id, p]));
    let salaryChanged = 0;
    let projectionChanged = 0;
    for (const player of currPool.players ?? []) {
      const prevPlayer = prevByPlayer.get(player.mlb_player_id ?? player.dk_player_id);
      if (!prevPlayer) continue;
      if (prevPlayer.salary !== player.salary) salaryChanged += 1;
      if (prevPlayer.projection !== player.projection) projectionChanged += 1;
    }
    report.salaryChangedCount = salaryChanged;
    report.projectionChangedCount = projectionChanged;
  } else {
    report.notes.push("Player pool missing for one of the two runs -- cannot compare salaries/projections.");
  }

  const prevOwnership = safeReadJson<OwnershipSnapshot>(stepPath(previous, "ownership"));
  const currOwnership = safeReadJson<OwnershipSnapshot>(stepPath(current, "ownership"));
  if (prevOwnership && currOwnership) {
    const prevByPlayer = new Map((prevOwnership.players ?? []).map((p) => [p.mlb_player_id ?? p.dk_player_id, p]));
    let changed = 0;
    for (const player of currOwnership.players ?? []) {
      const prevPlayer = prevByPlayer.get(player.mlb_player_id ?? player.dk_player_id);
      if (prevPlayer && Math.abs(prevPlayer.projected_ownership - player.projected_ownership) >= 1) changed += 1;
    }
    report.ownershipChangedCount = changed;
  } else {
    report.notes.push("Ownership snapshot missing for one of the two runs -- cannot compare ownership.");
  }

  const prevLineups = safeReadJson<LineupSet>(previous.summary.lineupSetPaths?.projection ?? null);
  const currLineups = safeReadJson<LineupSet>(current.summary?.lineupSetPaths?.projection ?? null);
  if (prevLineups && currLineups) {
    const prevExposure = exposurePercentByName(prevLineups);
    const currExposure = exposurePercentByName(currLineups);
    const names = new Set([...prevExposure.keys(), ...currExposure.keys()]);
    const changes: ExposureChange[] = [];
    for (const name of names) {
      const beforePercent = prevExposure.get(name) ?? null;
      const afterPercent = currExposure.get(name) ?? null;
      if (beforePercent !== afterPercent) changes.push({ name, beforePercent, afterPercent });
    }
    changes.sort(
      (a, b) => Math.abs((b.afterPercent ?? 0) - (b.beforePercent ?? 0)) - Math.abs((a.afterPercent ?? 0) - (a.beforePercent ?? 0)),
    );
    report.exposureChanges = changes;
  } else {
    report.notes.push("Projection-portfolio lineups missing for one of the two runs -- cannot compare exposure.");
  }

  return report;
}
