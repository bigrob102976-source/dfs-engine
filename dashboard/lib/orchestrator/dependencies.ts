import type { PipelineStepId } from "./types";

export const STEP_ORDER: PipelineStepId[] = ["research", "pitchers", "batters", "dfsSalaries", "playerPool", "ownership", "optimizer"];

/** What each pregame pipeline step requires before it can run, per
 * Milestone 16's explicit dependency rules:
 *  - Pitcher/Batter Agent both need the Research Package.
 *  - DFS Salaries (the provider fetch) needs the Research Package (the
 *    mock provider reads it to build slate/player structure).
 *  - Player Pool needs Pitcher + Batter snapshots AND a ready DFS
 *    salary/slate fetch (it joins all three).
 *  - Ownership needs the Player Pool.
 *  - Optimizer needs the Player Pool and Ownership. */
const STEP_DEPENDENCIES: Record<PipelineStepId, PipelineStepId[]> = {
  research: [],
  pitchers: ["research"],
  batters: ["research"],
  dfsSalaries: ["research"],
  playerPool: ["research", "pitchers", "batters", "dfsSalaries"],
  ownership: ["playerPool"],
  optimizer: ["playerPool", "ownership"],
};

/** The full set of steps needed to bring every one of `targets` to
 * ready, in pipeline execution order (a step's dependencies always
 * appear before it). Used by the "smart" (missing-data-only) refresh
 * mode in runner.ts to decide which steps to even attempt -- a step NOT
 * in this closure is marked "skipped" and never invoked, regardless of
 * whether its artifact happens to already exist. */
export function resolveStepChain(targets: PipelineStepId[]): PipelineStepId[] {
  const closure = new Set<PipelineStepId>();
  function visit(step: PipelineStepId) {
    if (closure.has(step)) return;
    for (const dep of STEP_DEPENDENCIES[step]) visit(dep);
    closure.add(step);
  }
  for (const target of targets) visit(target);
  return STEP_ORDER.filter((step) => closure.has(step));
}
