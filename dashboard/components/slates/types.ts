export interface SlateManagerRow {
  slateId: string;
  slateName: string | null;
  gameCount: number | null;
  playerCount: number | null;
  startTime: string | null;
  status: "READY" | "PARTIAL" | "MISSING";
  /** Milestone 27.4 -- dfs/providers/source_provenance.py's classification
   * for this slate's player pool (from its dk_match_report_*.json), null
   * when no pool has been built yet for this slate so there's nothing to
   * classify. Never invented client-side -- read straight from the report
   * dfs/pool_builder.py already wrote. */
  sourceProvenance: string | null;
  realismBlocked: boolean;
}
