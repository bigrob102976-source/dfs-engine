import type { OptimizerPoolResult, SlateListResult } from "../optimizerWorkspace/types";

// M5A -- provider-neutral serving interface. Exactly two implementations
// exist (LegacyR2ServingBackend, CanonicalPostgresServingBackend) and
// both return the EXACT SAME domain shapes (SlateListResult,
// OptimizerPoolResult) the UI/optimizer already consume -- callers never
// need to know which backend actually served a request.
export type ServingBackendKind = "LEGACY_R2" | "CANONICAL_POSTGRES";

export interface SlateServingBackend {
  readonly kind: ServingBackendKind;
  /** Mirrors poolCache.ts's listSlates(date) contract exactly -- never
   * throws; an unavailable/absent state is reported via the returned
   * SlateListResult.status, never an exception. */
  listSlates(date: string, sport?: string): Promise<SlateListResult>;
  /** Mirrors poolCache.ts's loadPool(date, slateId) contract: throws a
   * descriptive Error when the pool cannot be served (absent/invalid/
   * expired canonical data, or any legacy failure) -- callers already
   * handle this via try/catch (see app/api/optimizer/pool/route.ts). */
  getSlatePool(date: string, providerSlateId: string, sport?: string): Promise<OptimizerPoolResult>;
}
