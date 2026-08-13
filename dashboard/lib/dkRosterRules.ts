/** Mirror of config/dk_roster_config.py -- DraftKings Classic MLB roster
 * shape is a fixed, publicly-documented structural fact (not a scoring
 * or business-logic value the Python side computes), so duplicating it
 * here for fast client-side UI checks (position tabs, "too many locked
 * pitchers" pre-flight) is low-risk. The AUTHORITATIVE constraint
 * enforcement always happens server-side via the real optimizer
 * (optimizer/solver.py, optimizer/constraints.py) -- nothing here ever
 * decides what lineups are legal, only what the UI should warn about
 * before asking the server. */

export interface RosterSlotRule {
  slot: string;
  count: number;
}

export const DK_CLASSIC_ROSTER_SLOTS: RosterSlotRule[] = [
  { slot: "P", count: 2 },
  { slot: "C", count: 1 },
  { slot: "1B", count: 1 },
  { slot: "2B", count: 1 },
  { slot: "3B", count: 1 },
  { slot: "SS", count: 1 },
  { slot: "OF", count: 3 },
];

export const DK_ROSTER_SIZE = DK_CLASSIC_ROSTER_SLOTS.reduce((sum, s) => sum + s.count, 0);

export const DK_CLASSIC_SALARY_CAP = 50000;

export const DK_MAX_HITTERS_PER_TEAM = 5;

export const POSITION_TABS = ["ALL", "P", "C", "1B", "2B", "3B", "SS", "OF"] as const;
export type PositionTab = (typeof POSITION_TABS)[number];

export const OPTIMIZER_OBJECTIVES = [
  { value: "projection", label: "Projection", explanation: "Maximize median projection." },
  { value: "ceiling", label: "Ceiling", explanation: "Favor upside." },
  { value: "balanced", label: "Balanced", explanation: "Projection + ceiling." },
  { value: "leverage", label: "Leverage", explanation: "Projection quality adjusted by projected ownership/leverage." },
] as const;

export const LINEUP_COUNT_OPTIONS = [1, 5, 10, 20, 50, 100, 150];

/** Primary-stack presets the (single-stack) optimizer can actually
 * enforce today. Presets that require a SECOND, independent team stack
 * (5/2, 5/3, 4/4, 4/3/1) are listed separately in
 * SECONDARY_STACK_PRESETS_PLANNED, disabled -- the optimizer's CP-SAT
 * model only supports one required team stack per lineup (see
 * optimizer/solver.py; grepped repo-wide, no secondary/multi-stack
 * concept exists anywhere). Not faking support for those. */
export const PRIMARY_STACK_PRESETS = [
  { label: "No Forced Stack", size: null },
  { label: "3", size: 3 },
  { label: "4", size: 4 },
  { label: "5", size: 5 },
];

export const SECONDARY_STACK_PRESETS_PLANNED = ["5 / 2", "5 / 3", "4 / 4", "4 / 3 / 1"];

export const MIN_UNIQUE_OPTIONS = [1, 2, 3, 4];
