import path from "node:path";

/**
 * The mlb-dfs-engine project root, where every artifact directory
 * (research_output/, predictions/, ownership_predictions/, dfs_input/,
 * lineups/, ownership_evaluations/, evaluations/, actual_ownership/) lives.
 *
 * Defaults to the parent of this Next.js app (dashboard/ is created
 * directly inside mlb-dfs-engine/), overridable via MLB_DFS_ROOT for
 * tests or alternate layouts. This dashboard never writes into this
 * tree -- it only reads.
 */
export function getArtifactRoot(): string {
  return process.env.MLB_DFS_ROOT
    ? path.resolve(process.env.MLB_DFS_ROOT)
    : path.resolve(process.cwd(), "..");
}

export const ARTIFACT_DIRS = {
  research: "research_output",
  predictions: "predictions",
  ownershipPredictions: "ownership_predictions",
  dfsInput: "dfs_input",
  lineups: "lineups",
  ownershipEvaluations: "ownership_evaluations",
  pitcherEvaluations: "evaluations",
  actualOwnership: "actual_ownership",
  externalProjectionSnapshots: "external_projection_snapshots",
  adjustedProjectionSnapshots: "adjusted_projection_snapshots",
  gameEnvironmentSnapshots: "game_environment_snapshots",
  aiProjectionSnapshots: "ai_projection_snapshots",
  nativeProjectionSnapshots: "native_projection_snapshots",
  // Milestone 27: postgame actual DK fantasy points (results/<date>/
  // {pitcher,hitter}_results.json) -- date-scoped only, by design (a
  // player's real stat line doesn't depend on which DK slate you view
  // it through; see evaluation/results_collector.py).
  results: "results",
} as const;

export function artifactPath(...segments: string[]): string {
  return path.join(getArtifactRoot(), ...segments);
}
