import { isAdminRole } from "./auth/roles";
import { getCurrentUser } from "./auth/session";
import { listPublishedSlateIds } from "./db/slateStatus";
import type { SlateOption } from "./orchestrator/types";
import type { ServingBackendKind } from "./servingBackend/types";

/** Milestone 29: the ONE shared rule for "which slates can this viewer
 * see" -- ADMIN sees every lifecycle state (Draft/Processing/Ready/...),
 * everyone else sees only slates that are PUBLISHED for `date` in the
 * sense the serving backend that produced them defines. Used by both
 * lib/slateContext.ts (every /dashboard/* page) and
 * /api/optimizer/slates (the Optimizer's own slate picker) so a
 * draft/unprocessed admin slate can never leak into a member-facing
 * list from either path. Reads the viewer's role itself (via
 * getCurrentUser()) rather than requiring every caller to pass it
 * through, so this stays a single, hard-to-bypass choke point -- see
 * this project's "Enforce server-side" requirement.
 *
 * `backendKind` exists because "published" is backend-specific:
 *
 *  - LEGACY_R2 (the default, and what every existing caller gets unless
 *    it says otherwise): publication is an explicit, separate step
 *    recorded in the legacy `slate_status` table, so that table is the
 *    authority and is consulted below.
 *
 *  - CANONICAL_POSTGRES: there is no separate publish step. A canonical
 *    slate only becomes visible to canonicalListSlates() at all once
 *    validation_state = 'VALID', and that value is written ONLY by the
 *    successful-promotion path in lib/db/canonicalPromotion.ts, in the
 *    same upsert that sets promoted_at -- a rejected attempt goes
 *    through recordRejectedAttempt(), which is unreachable unless
 *    validationState !== 'VALID'. So "returned by canonicalListSlates"
 *    already means "promoted", and consulting slate_status here would
 *    be checking a table the canonical pipeline never writes to. That
 *    is not a theoretical mismatch: it made every member see zero
 *    slates (slate_status's newest row was 2026-09-05 while canonical
 *    had three healthy promoted slates for the day).
 *
 * The admin-CSV exclusion below is deliberately INDEPENDENT of all of
 * this and applies to every backend. */
export async function filterSlatesForCurrentViewer(
  slates: SlateOption[], date: string, backendKind: ServingBackendKind = "LEGACY_R2",
): Promise<SlateOption[]> {
  const user = await getCurrentUser();
  if (user && isAdminRole(user.role)) return slates;
  // BREAK-GLASS ADMIN CSV UPLOAD Phase 8: explicit, independent
  // exclusion -- an admin-CSV-imported canonical slate must never reach
  // a non-admin viewer. Nothing ever calls the legacy `slate_status`
  // publish flow for one (so the check below would already exclude it
  // today too), but that's this OTHER mechanism's job to guarantee, not
  // this one's -- a future change to the legacy publish flow must not be
  // able to silently expose admin-CSV data by accident.
  const nonAdminCsvSlates = slates.filter((s) => s.provider !== "draftkings_csv");
  // Promotion IS publication for canonical -- see this function's
  // docstring. The admin-CSV exclusion above still applies.
  if (backendKind === "CANONICAL_POSTGRES") return nonAdminCsvSlates;
  const publishedIds = new Set(await listPublishedSlateIds(date));
  return nonAdminCsvSlates.filter((s) => publishedIds.has(s.slateId));
}
