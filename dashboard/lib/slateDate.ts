// Milestone 31.2C: one shared date-normalization/validation helper for
// every route/page in the "select a slate date" chain (admin slates ->
// process/refresh -> optimizer pool -> dashboard pages), replacing the
// three near-identical `DATE_RE = /^\d{4}-\d{2}-\d{2}$/` regexes that
// were previously duplicated (and only shape-checked, never calendar-
// validated) across app/api/admin/slates/{status,process,refresh}/route.ts.
//
// getTodayEasternDate() remains the sole "no explicit date supplied"
// fallback everywhere -- this module only decides whether an explicit
// candidate string is a real, valid calendar date, never what "today"
// means.

import { getTodayEasternDate } from "./currentDate";

const SHAPE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** True only for a string shaped YYYY-MM-DD that is also a real
 * calendar date (rejects e.g. "2026-02-30", "2026-13-01") -- guards
 * against an invalid-but-shape-valid string ever reaching an artifact
 * path or a provider call. */
export function isValidSlateDateString(value: unknown): value is string {
  if (typeof value !== "string" || !SHAPE_RE.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

export type SlateDateResolution = { ok: true; date: string } | { ok: false; error: string };

/** Resolves an explicit, optional slate-date candidate (a query param or
 * request-body field) per Milestone 31.2C's Part 2 contract:
 *   - absent/null/empty string  -> Eastern-today (the authoritative MLB
 *     slate-date definition, see currentDate.ts -- fully backward
 *     compatible in shape with every pre-M31.2C caller that never sent
 *     a date, just correctly timezoned now).
 *   - a valid YYYY-MM-DD string -> used as-is.
 *   - anything else present     -> rejected (`ok: false`) rather than
 *     silently falling back to today, per Part 3's "reject malformed
 *     dates" -- a caller that DID try to specify a date deserves a 400,
 *     not a silent switch to a different date than the one it asked for. */
export function resolveSlateDate(candidate: unknown): SlateDateResolution {
  if (candidate === undefined || candidate === null || candidate === "") return { ok: true, date: getTodayEasternDate() };
  if (isValidSlateDateString(candidate)) return { ok: true, date: candidate };
  return { ok: false, error: '`date` must be a valid calendar date in YYYY-MM-DD format.' };
}
