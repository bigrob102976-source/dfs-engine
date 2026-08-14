/** DraftKings' own MLB slate-type names (Milestone 19). Purely a
 * labeling convenience for the upload widget's dropdown -- DraftKings'
 * CSV export itself has no field that names the slate, so the user
 * tags each upload with one of these (or types a custom one) so
 * multiple real slates can coexist for the same date. */
export const DK_SLATE_LABELS = ["Main", "Turbo", "Night", "Late", "Afternoon", "Showdown"] as const;
