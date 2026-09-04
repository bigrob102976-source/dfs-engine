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

/** Multi-team stacks (M2): every stack shape the optimizer's CP-SAT model
 * actually enforces (optimizer/solver.py -- a plain single-team stack via
 * `stackSize`/`stackTeam`, or a second, independent team stack layered on
 * top via `stackSize2`/`stackTeam2`). `requiresSecondaryTeam` is what
 * ConstraintsPanel.tsx uses to decide whether to show the Secondary Team
 * selector at all -- never rendering a control that isn't wired through
 * to a real constraint. */
export interface StackTypeOption {
  label: string;
  stackSize: number | null;
  stackSize2: number | null;
  requiresSecondaryTeam: boolean;
}

export const STACK_TYPE_OPTIONS: StackTypeOption[] = [
  { label: "None", stackSize: null, stackSize2: null, requiresSecondaryTeam: false },
  { label: "3", stackSize: 3, stackSize2: null, requiresSecondaryTeam: false },
  { label: "4", stackSize: 4, stackSize2: null, requiresSecondaryTeam: false },
  { label: "5", stackSize: 5, stackSize2: null, requiresSecondaryTeam: false },
  { label: "5-3", stackSize: 5, stackSize2: 3, requiresSecondaryTeam: true },
  { label: "5-2", stackSize: 5, stackSize2: 2, requiresSecondaryTeam: true },
  { label: "4-4", stackSize: 4, stackSize2: 4, requiresSecondaryTeam: true },
  { label: "4-3", stackSize: 4, stackSize2: 3, requiresSecondaryTeam: true },
];

export const MIN_UNIQUE_OPTIONS = [1, 2, 3, 4];
