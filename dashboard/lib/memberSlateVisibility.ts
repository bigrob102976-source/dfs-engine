import { isAdminRole } from "./auth/roles";
import { getCurrentUser } from "./auth/session";
import { listPublishedSlateIds } from "./db/slateStatus";
import type { SlateOption } from "./orchestrator/types";

/** Milestone 29: the ONE shared rule for "which slates can this viewer
 * see" -- ADMIN sees every lifecycle state (Draft/Processing/Ready/...),
 * everyone else sees ONLY slates lib/db/slateStatus.ts currently has
 * published for `date`. Used by both lib/slateContext.ts (every
 * /dashboard/* page) and /api/optimizer/slates (the Optimizer's own
 * slate picker) so a draft/unprocessed admin slate can never leak into
 * a member-facing list from either path. Reads the viewer's role itself
 * (via getCurrentUser()) rather than requiring every caller to pass it
 * through, so this stays a single, hard-to-bypass choke point -- see
 * this project's "Enforce server-side" requirement. */
export async function filterSlatesForCurrentViewer(slates: SlateOption[], date: string): Promise<SlateOption[]> {
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
  const publishedIds = new Set(await listPublishedSlateIds(date));
  return nonAdminCsvSlates.filter((s) => publishedIds.has(s.slateId));
}
