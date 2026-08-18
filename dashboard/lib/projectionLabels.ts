// Milestone 27 -- Part 3: canonical, unambiguous projection-source
// display names, used everywhere a projection column/label appears
// (Hitters, Pitchers, Optimizer, Player Detail, Projection Lab) so no
// column is ever labeled a bare, ambiguous "Projection" when multiple
// sources exist. Single source of truth -- every page imports these
// constants rather than hardcoding its own copy.

export const PROJECTION_LABELS = {
  blueCollar: "BLUECOLLAR",
  native: "BIG MONEY NATIVE",
  ai: "BIG MONEY AI",
  actual: "ACTUAL DK",
  legacy: "LEGACY",
} as const;

/** The Optimizer's "external" projection slot is generic (whatever the
 * currently-loaded external_projections/ baseline is) -- today the only
 * real, supported provider behind it is BlueCollar (imported via the
 * Universal Projection Import Center; see external_projections/csv_import/).
 * This resolves the HONEST label for that slot from the baseline's own
 * `provider_name`, never presenting a different provider (e.g. the mock
 * provider) as if it were BlueCollar. Returns "BlueCollar" (the expected/
 * default case) when nothing is loaded yet, since that IS what the slot
 * is FOR even while disabled -- callers gate on `hasExternalProjections`
 * separately to decide enabled/disabled, not on this label. */
export function resolveExternalSourceLabel(providerName: string | null): string {
  if (providerName === "BlueCollar DFS") return "BlueCollar";
  if (providerName) return "External Other";
  return "BlueCollar";
}

/** "-- " for a value that genuinely doesn't exist yet (not zero, not an
 * error) -- the milestone's explicit "NOT LOADED" honesty requirement
 * for BlueCollar and Actual DK cells. */
export function formatProjectionCell(value: number | null, notLoadedLabel = "--"): string {
  return value === null ? notLoadedLabel : value.toFixed(1);
}

export function formatDelta(value: number | null): string {
  if (value === null) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}`;
}
