/** Resolves "today" for MLB DFS slate purposes: America/New_York
 * (Eastern) -- the SAME timezone canonical/slate_date.py's own
 * slateDate contract uses (the US/Eastern calendar date of a slate's
 * first real game-start instant), so the customer-facing "what day is
 * it" question and the canonical Postgres partition a slate is actually
 * stored under always agree. This was previously America/Chicago
 * (Central) -- a real, confirmed-live bug: Chicago lags Eastern by
 * exactly one hour, every day, so for the hour between Eastern midnight
 * and Chicago midnight this function used to keep reporting the OLD
 * calendar date even after a real, already-published, already-promoted
 * DraftKings slate existed in canonical Postgres under the NEW Eastern
 * date -- silently hiding a real slate from every customer (and, since
 * the external worker's own date computation had the identical bug,
 * leaving that new date's eligibility/projections/ownership uncomputed
 * for up to another hour on top of that). Renamed from
 * getTodayChicagoDate to getTodayEasternDate for the same reason this
 * bug existed in the first place: an honestly-named function is harder
 * to silently reintroduce a timezone mismatch against.
 *
 * Node 20+ ships full ICU, so Intl.DateTimeFormat works with no extra
 * timezone-data dependency. The "en-CA" locale is a deliberate trick --
 * it's the one built-in locale whose default date format is already
 * YYYY-MM-DD, so no manual reassembly of parts is needed. */
export function getTodayEasternDate(now: Date = new Date()): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(now);
}
