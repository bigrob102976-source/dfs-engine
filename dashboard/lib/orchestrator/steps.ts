import type { PipelineStepId, StepResult } from "./types";

/** The 7 pipeline stages shown on the dashboard, in execution order.
 * "optimizer" bundles all three objective runs (Projection/Balanced/
 * Leverage) internally -- the milestone's UI spec lists Optimizer as a
 * single status row, with the per-objective lineup counts reported in
 * the run summary instead of as separate rows. */
export const STEP_DEFINITIONS: ReadonlyArray<{ id: PipelineStepId; label: string }> = [
  { id: "research", label: "Research Package" },
  { id: "pitchers", label: "Pitcher Agent" },
  { id: "batters", label: "Batter Agent" },
  { id: "dfsSalaries", label: "DFS Salaries" },
  { id: "playerPool", label: "Player Pool" },
  { id: "ownership", label: "Ownership" },
  { id: "optimizer", label: "Optimizer" },
];

export function initialSteps(): StepResult[] {
  return STEP_DEFINITIONS.map((def) => ({
    id: def.id,
    label: def.label,
    status: "waiting",
    startedAt: null,
    finishedAt: null,
    message: null,
    artifactPath: null,
    command: null,
    stdoutTail: null,
    stderrTail: null,
  }));
}
