export interface SlateManagerRow {
  slateId: string;
  slateName: string | null;
  gameCount: number | null;
  playerCount: number | null;
  startTime: string | null;
  status: "READY" | "PARTIAL" | "MISSING";
}
