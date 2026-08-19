import type { PlayerRow } from "./types";

// Milestone 30.1: page-level eligibility filtering, built on top of the
// PlayerRow.eligibilityStatus field lib/normalize.ts already carries
// through from dfs/eligibility.py. Kept separate from the generic
// lib/sortFilter.ts filter system (team/position/salary/etc.) since this
// is a fixed, small vocabulary specific to pitcher/hitter pages, not a
// free-form filter a user configures.

export type PitcherEligibilityFilter = "starting" | "all" | "relief" | "unmatched";
export type HitterEligibilityFilter = "confirmed" | "all" | "bench" | "unconfirmed";

export const PITCHER_ELIGIBILITY_OPTIONS: Array<{ value: PitcherEligibilityFilter; label: string }> = [
  { value: "starting", label: "Starting Pitchers" },
  { value: "all", label: "All DK Pitchers" },
  { value: "relief", label: "Relief Pitchers" },
  { value: "unmatched", label: "Unmatched" },
];

export const HITTER_ELIGIBILITY_OPTIONS: Array<{ value: HitterEligibilityFilter; label: string }> = [
  { value: "confirmed", label: "Confirmed Starting Hitters" },
  { value: "all", label: "All DK Hitters" },
  { value: "bench", label: "Bench" },
  { value: "unconfirmed", label: "Waiting For Lineups" },
];

export function isPitcherEligibilityFilter(value: string | undefined): value is PitcherEligibilityFilter {
  return PITCHER_ELIGIBILITY_OPTIONS.some((o) => o.value === value);
}

export function isHitterEligibilityFilter(value: string | undefined): value is HitterEligibilityFilter {
  return HITTER_ELIGIBILITY_OPTIONS.some((o) => o.value === value);
}

// A row's eligibilityStatus is null only when no DK pool was matched to
// it at all (no pool loaded yet, or this specific research-board player
// has no DK row) -- see lib/normalize.ts. Every row that reaches this
// function via the RESEARCH board (pitchers.json/batters.json) is,
// by construction, already a probable starter / confirmed-lineup member
// (research/normalizer.py only ever includes those) -- so a null status
// is treated as starting-equivalent, never as "exclude this row." The
// one narrow imprecision this accepts: a DK-only row from a pool file
// saved BEFORE this milestone (no eligibility_status field at all) would
// also read as null and be treated as starting-equivalent even if it
// were really a reliever/bench player -- acceptable for old, pre-
// migration data; every pool built from here on always has a real value.
function isStartingEquivalent(status: string | null): boolean {
  return status === null || status === "STARTING_PITCHER";
}

function isConfirmedEquivalent(status: string | null): boolean {
  return status === null || status === "STARTING_HITTER";
}

export function filterPitcherRowsByEligibility(rows: PlayerRow[], filter: PitcherEligibilityFilter): PlayerRow[] {
  switch (filter) {
    case "starting":
      return rows.filter((r) => isStartingEquivalent(r.eligibilityStatus));
    case "relief":
      return rows.filter((r) => r.eligibilityStatus === "RELIEF_PITCHER");
    case "unmatched":
      return rows.filter((r) => r.eligibilityStatus === "UNMATCHED" || r.eligibilityStatus === "AMBIGUOUS");
    case "all":
    default:
      return rows;
  }
}

export function filterHitterRowsByEligibility(rows: PlayerRow[], filter: HitterEligibilityFilter): PlayerRow[] {
  switch (filter) {
    case "confirmed":
      return rows.filter((r) => isConfirmedEquivalent(r.eligibilityStatus));
    case "bench":
      return rows.filter((r) => r.eligibilityStatus === "BENCH");
    case "unconfirmed":
      return rows.filter((r) => r.eligibilityStatus === "LINEUP_UNCONFIRMED");
    case "all":
    default:
      return rows;
  }
}
