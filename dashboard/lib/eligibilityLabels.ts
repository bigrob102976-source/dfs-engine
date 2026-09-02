// T1F -- translates the raw dfs/eligibility.py status vocabulary into
// short, honest, member-readable labels for the optimizer player table.
// Never changes backend semantics: this is a pure display mapping, the
// same `eligibilityStatus` string PoolPlayerRow already carries through
// unchanged. An unconfirmed player is never relabeled as a starter.

export interface EligibilityLabel {
  label: string;
  tone: "starting" | "bench" | "unconfirmed" | "unresolved";
}

const ELIGIBILITY_LABELS: Record<string, EligibilityLabel> = {
  STARTING_HITTER: { label: "Starting", tone: "starting" },
  STARTING_PITCHER: { label: "Starting Pitcher", tone: "starting" },
  BENCH: { label: "Bench", tone: "bench" },
  RELIEF_PITCHER: { label: "Relief", tone: "bench" },
  LINEUP_UNCONFIRMED: { label: "Lineup Not Confirmed", tone: "unconfirmed" },
  SCRATCHED: { label: "Scratched", tone: "unresolved" },
  UNMATCHED: { label: "Identity Unresolved", tone: "unresolved" },
  AMBIGUOUS: { label: "Identity Ambiguous", tone: "unresolved" },
};

/** `status` is null only when eligibility hasn't been computed for this
 * row at all yet (never fabricated as "starting" or "confirmed"). */
export function formatEligibilityStatus(status: string | null): EligibilityLabel {
  if (status === null) return { label: "Not Computed", tone: "unconfirmed" };
  return ELIGIBILITY_LABELS[status] ?? { label: status, tone: "unresolved" };
}
