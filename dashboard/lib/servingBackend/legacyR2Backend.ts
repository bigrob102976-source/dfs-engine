import { listSlates, loadPool } from "../optimizerWorkspace/poolCache";
import type { SlateServingBackend } from "./types";

// M5A -- thin wrapper, ZERO behavior change: delegates to the exact same
// poolCache.ts functions every customer route has always called. `sport`
// is accepted for interface symmetry with CanonicalPostgresServingBackend
// but ignored -- poolCache.ts/the legacy R2 artifact layout has always
// been implicitly MLB-only (see poolCache.ts's own module docstring);
// this backend must never change that pre-M5 behavior.
export const LegacyR2ServingBackend: SlateServingBackend = {
  kind: "LEGACY_R2",
  listSlates: (date: string) => listSlates(date),
  getSlatePool: (date: string, providerSlateId: string) => loadPool(date, providerSlateId, false),
};
