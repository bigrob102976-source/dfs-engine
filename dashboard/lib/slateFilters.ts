// Milestone 26 -- pure, dependency-free slate-filtering helpers, split
// out of slateContext.ts specifically so CLIENT Components (e.g.
// components/layout/GlobalSlateSelector.tsx) can import them without
// pulling in slateContext.ts's server-only resolveSlateContext() (which
// transitively imports lib/optimizerWorkspace/poolCache.ts -> Node's
// `fs`/child_process -- Turbopack cannot bundle that for the browser).
// Server Components should generally import from slateContext.ts
// instead, which re-exports everything here for convenience.

import type { SlateOption, SlateContextLike } from "./orchestrator/types";

/** The effective game_ids filter for a resolved slate context: `null`
 * means "no filtering" (either no slate selected, or the selected
 * slate's game_ids couldn't be resolved). Every filterXBySlate() below
 * takes this same `string[] | null` shape. */
export function effectiveGameIds(context: SlateContextLike): string[] | null {
  const ids = context.selected?.gameIds ?? null;
  return ids && ids.length > 0 ? ids : null;
}

/** Filters any row carrying a `gameId` field (PlayerRow from
 * lib/normalize.ts, PoolPlayerRow, etc.) to a slate's games. `null`
 * gameIds -- no filtering (full day). Rows with a null gameId are
 * always dropped once a real filter is active (Milestone 26: no
 * player of unknown game may leak into a slate-scoped view). */
export function filterByGameIds<T extends { gameId: string | null }>(rows: T[], gameIds: string[] | null): T[] {
  if (gameIds === null) return rows;
  const set = new Set(gameIds);
  return rows.filter((r) => r.gameId !== null && set.has(r.gameId));
}

/** Same as filterByGameIds but for raw records keyed `game_id` (Game
 * Environment report games, research package records) instead of the
 * normalized `gameId` PlayerRow shape. */
export function filterByGameIdField<T extends { game_id: string }>(rows: T[], gameIds: string[] | null): T[] {
  if (gameIds === null) return rows;
  const set = new Set(gameIds);
  return rows.filter((r) => set.has(r.game_id));
}

/** Formats "Main — 9 Games" / "Turbo — 3 Games" style labels
 * consistently across the global selector, Slate Manager, and page
 * headers. */
export function formatSlateLabel(slate: SlateOption): string {
  const parts = [slate.slateName ?? slate.slateId];
  if (slate.gameCount !== null) parts.push(`${slate.gameCount} Game${slate.gameCount === 1 ? "" : "s"}`);
  return parts.join(" — ");
}
