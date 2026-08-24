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
export async function getArtifactStatus(date: string): Promise<ArtifactReadiness> {
  const [pool, research, pitchers, batters, dfsSalariesReady, ownership, optimizer] = await Promise.all([
    poolFingerprint(date),
    researchSlateFingerprint(date),
    pitcherSnapshotFingerprint(date),
    batterSnapshotFingerprint(date),
    isProviderSlateReady(date),
    ownershipFingerprint(date),
    lineupSetFingerprint(date),
  ]);
  const poolDoc = pool.path ? await safeReadJson<DKPlayerPool>(pool.path) : null;

  return {
    research: research.path !== null,
    pitchers: pitchers.path !== null,
    batters: batters.path !== null,
    dfsSalaries: dfsSalariesReady,
    playerPool: pool.path !== null && Boolean(poolDoc?.roster_feasibility_pass),
    ownership: ownership.path !== null,
    optimizer: optimizer.path !== null,
  };
}

async function isProviderSlateReady(date: string): Promise<boolean> {
  const fp = await providerSlateFingerprint(date);
  if (!fp.path) return false;
  const doc = await safeReadJson<Record<string, unknown>>(fp.path);
  return doc?.status === "ready";
}
