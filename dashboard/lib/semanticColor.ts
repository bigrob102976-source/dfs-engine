/** Milestone 32.6 Part 7 -- the ONE centralized GREEN/YELLOW/RED status
 * system for PERFORMANCE/QUALITY metrics across the dashboard.
 *
 *   GREEN  = GOOD
 *   YELLOW = MODERATE / CAUTION
 *   RED    = BAD
 *
 * The critical rule this file exists to enforce: color must never be
 * assigned by "is this number high" alone -- different metrics have
 * different directionality. A metric's `direction` says whether HIGH or
 * LOW is the good end:
 *
 *   HIGH_GOOD: Projection, Power, Matchup, Confidence/Data Quality,
 *              Value, Leverage, Team Implied Runs, Game Total (for a
 *              hitting-environment/stack view).
 *   LOW_GOOD:  Risk, Weather Risk, negative injury/weather concern.
 *
 * Confirmed real bug this fixes (lib/commandCenter.ts's Highest/Lowest
 * Total tiles had these backwards -- see the "vegasTotal" band below and
 * BottomInsights.tsx, which now derives tone from this module instead of
 * a hardcoded "negative"/"positive" literal).
 *
 * Pitcher-context note (per the milestone spec): the SAME raw Vegas
 * number can have opposite semantic meaning depending on whose
 * perspective it's scored from (a high total is good for a stack, but a
 * high OPPONENT implied total is bad for a pitcher) -- that distinction
 * is the CALLER's responsibility (pick the metric key matching the
 * actual perspective being displayed, e.g. "gameTotalHitting" vs a
 * pitcher-specific key), never something this generic scorer can infer
 * from the number alone.
 *
 * Accessibility: color is never the only signal -- every caller pairs a
 * `SemanticTone` with a text label (see toneLabel()) or an existing
 * text value (e.g. "82%"), never a bare colored dot/bar with no text.
 */

export type SemanticTone = "green" | "yellow" | "red";
export type SemanticDirection = "HIGH_GOOD" | "LOW_GOOD";

export interface ToneResult {
  tone: SemanticTone;
  label: string;
}

// --- 0-100 NORMALIZED SCORES (Projection quality, Power, Matchup,
// Confidence/Data Quality) -------------------------------------------------
// HIGH_GOOD: GREEN 70-100 / YELLOW 40-69.99 / RED 0-39.99.
// LOW_GOOD (Risk, Weather Risk): inverted -- GREEN 0-29.99 / YELLOW
// 30-59.99 / RED 60-100.
export const NORMALIZED_HIGH_GOOD_GREEN_MIN = 70;
export const NORMALIZED_HIGH_GOOD_YELLOW_MIN = 40;
export const NORMALIZED_LOW_GOOD_GREEN_MAX = 29.99;
export const NORMALIZED_LOW_GOOD_YELLOW_MAX = 59.99;

/** Mirrors research/game_environment/weather_risk.py's
 * WEATHER_RISK_GREEN_MAX/WEATHER_RISK_YELLOW_MAX exactly -- Python is
 * the source of truth (it computes the number), this is the display
 * mirror. Kept as its own named export (rather than reusing the generic
 * LOW_GOOD constants above) so the two can be changed independently if
 * weather risk's bands are ever tuned separately from generic Risk. */
export const WEATHER_RISK_GREEN_MAX = 29.99;
export const WEATHER_RISK_YELLOW_MAX = 59.99;

function toneForNormalized(value: number, direction: SemanticDirection): SemanticTone {
  if (direction === "HIGH_GOOD") {
    if (value >= NORMALIZED_HIGH_GOOD_GREEN_MIN) return "green";
    if (value >= NORMALIZED_HIGH_GOOD_YELLOW_MIN) return "yellow";
    return "red";
  }
  if (value <= NORMALIZED_LOW_GOOD_GREEN_MAX) return "green";
  if (value <= NORMALIZED_LOW_GOOD_YELLOW_MAX) return "yellow";
  return "red";
}

/** For a 0-100 score with a known direction (Confidence/Data Quality,
 * Power, Matchup, Risk, Weather Risk-via-generic-path, etc.). `null`
 * input (missing data) intentionally has no tone -- callers should show
 * "--" untoned rather than guessing a color for absent data. */
export function normalizedScoreTone(value: number | null, direction: SemanticDirection): ToneResult | null {
  if (value === null || Number.isNaN(value)) return null;
  const tone = toneForNormalized(value, direction);
  return { tone, label: toneLabel(tone) };
}

/** Weather Risk uses its own named thresholds (mirrors the Python
 * source-of-truth exactly) but is otherwise just a LOW_GOOD 0-100 score. */
export function weatherRiskTone(riskPercent: number | null): ToneResult | null {
  if (riskPercent === null || Number.isNaN(riskPercent)) return null;
  const tone: SemanticTone = riskPercent <= WEATHER_RISK_GREEN_MAX ? "green" : riskPercent <= WEATHER_RISK_YELLOW_MAX ? "yellow" : "red";
  return { tone, label: toneLabel(tone) };
}

// --- RAW/UNBOUNDED VALUES (Game Total, Team Implied Runs) -----------------
// No fixed baseball-number thresholds are hardcoded (a "9.5 is always
// the line" assumption ages badly and varies by park/season) -- ranked
// relative to the rest of the same slate instead: top third GREEN,
// middle third YELLOW, bottom third RED (reversed for LOW_GOOD raw
// metrics, e.g. a pitcher's opponent implied total).
export function percentileTone(value: number, allValues: number[], direction: SemanticDirection): ToneResult {
  const sorted = [...allValues].sort((a, b) => a - b);
  const index = sorted.indexOf(value);
  // Midpoint-of-bucket rank (not a raw <=-count fraction): guarantees the
  // strict min/max of a small slate always land in the bottom/top third
  // respectively, rather than a tie landing on a tercile boundary and
  // reading as "caution" for what is unambiguously this slate's most
  // extreme value.
  const rank = (index + 0.5) / sorted.length; // 0..1, higher = higher value
  const highGoodTone: SemanticTone = rank >= 2 / 3 ? "green" : rank >= 1 / 3 ? "yellow" : "red";
  const tone = direction === "HIGH_GOOD" ? highGoodTone : highGoodTone === "green" ? "red" : highGoodTone === "red" ? "green" : "yellow";
  return { tone, label: toneLabel(tone) };
}

export function toneLabel(tone: SemanticTone): string {
  switch (tone) {
    case "green":
      return "GOOD";
    case "yellow":
      return "CAUTION";
    case "red":
      return "BAD";
  }
}

export function toneTextClass(tone: SemanticTone): string {
  switch (tone) {
    case "green":
      return "text-green";
    case "yellow":
      return "text-yellow";
    case "red":
      return "text-red";
  }
}

export function toneBadgeClass(tone: SemanticTone): string {
  switch (tone) {
    case "green":
      return "bg-green/15 text-green";
    case "yellow":
      return "bg-yellow/15 text-yellow";
    case "red":
      return "bg-red/15 text-red";
  }
}
