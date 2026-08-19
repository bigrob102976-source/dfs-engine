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
  const publishedIds = new Set(listPublishedSlateIds(date));
  return slates.filter((s) => publishedIds.has(s.slateId));
}
