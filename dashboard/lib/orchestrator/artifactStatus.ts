import { safeReadJson } from "../discovery";
import type { DKPlayerPool } from "../types";
import {
  batterSnapshotFingerprint,
  lineupSetFingerprint,
  ownershipFingerprint,
  pitcherSnapshotFingerprint,
  poolFingerprint,
  providerSlateFingerprint,
  researchSlateFingerprint,
} from "./artifacts";
import type { PipelineStepId } from "./types";

export type ArtifactReadiness = Record<PipelineStepId, boolean>;

/** Read-only "is this pipeline step's artifact already present for
 * `date`" check -- no side effects, safe to call on every page render.
 * Shared by the "smart" (missing-data-only) refresh's skip-if-ready
 * logic (runner.ts) and the read-only Slate Readiness / MissingDataState
 * displays, so both agree on what "ready" means. A pool only counts as
 * ready if it can actually fill a legal roster (roster_feasibility_pass),
 * not merely if the file exists -- an infeasible pool isn't useful data. */
export function getArtifactStatus(date: string): ArtifactReadiness {
  const pool = poolFingerprint(date);
  const poolDoc = pool.path ? safeReadJson<DKPlayerPool>(pool.path) : null;

  return {
    research: researchSlateFingerprint(date).path !== null,
    pitchers: pitcherSnapshotFingerprint(date).path !== null,
    batters: batterSnapshotFingerprint(date).path !== null,
    dfsSalaries: isProviderSlateReady(date),
    playerPool: pool.path !== null && Boolean(poolDoc?.roster_feasibility_pass),
    ownership: ownershipFingerprint(date).path !== null,
    optimizer: lineupSetFingerprint(date).path !== null,
  };
}

function isProviderSlateReady(date: string): boolean {
  const fp = providerSlateFingerprint(date);
  if (!fp.path) return false;
  const doc = safeReadJson<Record<string, unknown>>(fp.path);
  return doc?.status === "ready";
}
