import type { OptimizerPoolResult } from "./types";

export interface ConstraintState {
  locks: string[]; // dkPlayerId
  exclusions: string[];
  maxExposure: Record<string, number>; // dkPlayerId -> fraction
}

export interface ReconcileResult {
  state: ConstraintState;
  warnings: string[];
}

/** Reconciles locks/exclusions/exposures against a (possibly new or
 * refreshed) player pool:
 *  - any id no longer present in the pool at all is dropped silently
 *    (the normal case on a slate change -- constraints from one slate
 *    never apply to another).
 *  - any LOCKED id whose player is present but no longer
 *    optimizer_eligible (e.g. scratched, or bumped to BENCH/RELIEF_PITCHER
 *    after a refresh -- see dfs/eligibility.py) is dropped WITH a
 *    warning -- a stale lock must never be silently kept.
 * Exclusions/exposures of an inactive player are harmless to keep (an
 * inactive player can't be rostered anyway), so only locks warn. */
export function reconcileConstraintsWithPool(pool: OptimizerPoolResult, current: ConstraintState): ReconcileResult {
  const byId = new Map(pool.players.map((p) => [p.dkPlayerId, p]));
  const warnings: string[] = [];

  const locks = current.locks.filter((id) => {
    const player = byId.get(id);
    if (!player) return false;
    if (!player.optimizerEligible) {
      warnings.push(`Locked player ${player.name} is no longer active.`);
      return false;
    }
    return true;
  });

  const exclusions = current.exclusions.filter((id) => byId.has(id));

  const maxExposure: Record<string, number> = {};
  for (const [id, fraction] of Object.entries(current.maxExposure)) {
    if (byId.has(id)) maxExposure[id] = fraction;
  }

  return { state: { locks, exclusions, maxExposure }, warnings };
}
