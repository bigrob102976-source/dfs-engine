// Milestone 26 -- Automatic Slate Separation + Global Slate Selector.
//
// Root cause this fixes: every page except the Optimizer read date-only
// full-day snapshots (research_output/, game_environment_snapshots/,
// ownership_predictions/, native/ai projection snapshots) with no
// concept of "which DraftKings slate" at all. This module is the ONE
// shared SERVER-SIDE helper every page uses to resolve "what slates
// exist for this date" + "which one (if any) is selected" from a
// `?slate=<id>` URL query param -- so there is exactly one place slate
// resolution logic lives, not seven slightly-different copies.
//
// SERVER-ONLY: this file imports lib/optimizerWorkspace/poolCache.ts,
// which shells out to Python (Node's child_process/fs) -- it must never
// be imported from a Client Component (Turbopack cannot bundle Node
// built-ins for the browser). The pure filtering/formatting helpers
// (effectiveGameIds, filterByGameIds, filterByGameIdField,
// formatSlateLabel) live in lib/slateFilters.ts instead, which has no
// such dependency and is safe for client code (see
// components/layout/GlobalSlateSelector.tsx) -- re-exported below so
// Server Component pages can still import everything from this one file.
//
// No slate selected (the default, pre-Milestone-26-compatible state) ==
// the full MLB day, unfiltered -- selecting a slate is an explicit user
// action (the global dropdown), never inferred/auto-picked, so nothing
// about existing behavior changes until the user opts in.

import { filterSlatesForCurrentViewer } from "./memberSlateVisibility";
import { listSlates } from "./optimizerWorkspace/poolCache";
import type { SlateOption } from "./orchestrator/types";

export { effectiveGameIds, filterByGameIdField, filterByGameIds, formatSlateLabel } from "./slateFilters";

export interface SlateContext {
  slates: SlateOption[];
  selected: SlateOption | null;
  status: "ready" | "not_connected" | "unavailable" | "auth_failed" | "no_slate";
  isMock: boolean;
  providerName: string | null;
  /** True when `selected` is set but its game_ids couldn't be resolved
   * (e.g. no Research Package pulled yet) -- callers should show
   * everything unfiltered rather than silently rendering zero rows, and
   * may want to surface this to the user. */
  gameIdsUnavailable: boolean;
}

/** Resolves available slates for `date` and, if `requestedSlateId` names
 * one of them, the selected slate. Never auto-selects a default -- an
 * unmatched/absent `requestedSlateId` simply means "no slate selected"
 * (full-day view), not an error -- UNLESS `autoSelectSoleSlate` is
 * explicitly opted into (Command Center only, per Milestone 29's "auto-
 * load the latest published slate when only one exists" requirement).
 *
 * Milestone 29: `slates` is filtered to PUBLISHED-only for anyone who
 * isn't ADMIN (lib/memberSlateVisibility.ts) -- a draft/processing/
 * unpublished slate can never appear in a member's slate list or be
 * silently selectable via a stale `?slate=` URL, enforced here (server-
 * side, the one place every /dashboard/* page's slate list flows
 * through) rather than by hiding a UI control. */
export async function resolveSlateContext(
  date: string, requestedSlateId?: string | null, options?: { autoSelectSoleSlate?: boolean },
): Promise<SlateContext> {
  const result = await listSlates(date);
  const slates = await filterSlatesForCurrentViewer(result.slates, date);
  let selected = requestedSlateId ? (slates.find((s) => s.slateId === requestedSlateId) ?? null) : null;
  if (!requestedSlateId && !selected && options?.autoSelectSoleSlate && slates.length === 1) {
    selected = slates[0];
  }

  return {
    slates,
    selected,
    status: result.status,
    isMock: result.isMock,
    providerName: result.providerName,
    gameIdsUnavailable: selected !== null && selected.gameIds.length === 0,
  };
}
