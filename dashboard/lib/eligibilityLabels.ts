// T1F (extended by the PROBABLE FIX milestone) -- translates the raw
// dfs/eligibility.py status vocabulary into short, honest,
// member-readable labels for the optimizer player table. Never changes
// backend semantics: this is a pure display mapping, the same
// `eligibilityStatus`/`lineupConfirmation` PoolPlayerRow already carries
// through unchanged. An unconfirmed or merely-probable player is never
// relabeled as a confirmed starter.

export interface EligibilityLabel {
  label: string;
  tone: "starting" | "probable" | "bench" | "unconfirmed" | "unresolved";
}

const ELIGIBILITY_LABELS: Record<string, EligibilityLabel> = {
  STARTING_HITTER: { label: "Confirmed Starter", tone: "starting" },
  // STARTING_PITCHER's own label is decided by formatEligibilityStatus
  // below (it alone also carries lineupConfirmation) -- this entry is
  // the fallback for the rare case lineupConfirmation is unavailable.
  STARTING_PITCHER: { label: "Starting Pitcher", tone: "starting" },
  PROBABLE_HITTER: { label: "Probable Starter", tone: "probable" },
  BENCH: { label: "Bench", tone: "bench" },
  RELIEF_PITCHER: { label: "Relief", tone: "bench" },
  OUT: { label: "Out", tone: "unresolved" },
  LINEUP_UNCONFIRMED: { label: "Unknown", tone: "unconfirmed" },
  SCRATCHED: { label: "Scratched", tone: "unresolved" },
  UNMATCHED: { label: "Identity Unresolved", tone: "unresolved" },
  AMBIGUOUS: { label: "Identity Ambiguous", tone: "unresolved" },
};

/** `status` is null only when eligibility hasn't been computed for this
 * row at all yet (never fabricated as "starting" or "confirmed").
 * `lineupConfirmation` ("CONFIRMED" | "PROBABLE" | null) additionally
 * distinguishes a probable vs. officially confirmed STARTING_PITCHER --
 * PROBABLE_HITTER already carries its own distinct label above and
 * never needs this parameter to read correctly. */
export function formatEligibilityStatus(status: string | null, lineupConfirmation?: string | null): EligibilityLabel {
  if (status === null) return { label: "Not Computed", tone: "unconfirmed" };
  if (status === "STARTING_PITCHER") {
    if (lineupConfirmation === "PROBABLE") return { label: "Probable Starter", tone: "probable" };
    if (lineupConfirmation === "CONFIRMED") return { label: "Confirmed Starter", tone: "starting" };
    // Confirmation genuinely not provided (e.g. a caller that predates
    // this milestone) -- never guess which one it is.
    return ELIGIBILITY_LABELS.STARTING_PITCHER;
  }
  return ELIGIBILITY_LABELS[status] ?? { label: status, tone: "unresolved" };
}
