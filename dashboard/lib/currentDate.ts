/** Resolves "today" for DFS slate purposes: America/Chicago, since that's
 * the DK/MLB DFS operating timezone this project standardizes on
 * elsewhere (see research/prediction_snapshot.py's _timezone_metadata).
 * Node 20+ ships full ICU, so Intl.DateTimeFormat works with no extra
 * timezone-data dependency. The "en-CA" locale is a deliberate trick --
 * it's the one built-in locale whose default date format is already
 * YYYY-MM-DD, so no manual reassembly of parts is needed. */
export function getTodayChicagoDate(now: Date = new Date()): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(now);
}
