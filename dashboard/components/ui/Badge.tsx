/** Table-color semantics (design system spec): green = positive,
 * amber(yellow) = neutral, red = negative, blue = interactive,
 * gold = premium, purple = AI. Never rainbow -- every badge in this
 * file draws from exactly that six-color set. */

const BADGE_BASE = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide";

function toneClasses(tone: "positive" | "neutral" | "negative" | "interactive"): string {
  switch (tone) {
    case "positive":
      return "bg-green/15 text-green";
    case "negative":
      return "bg-red/15 text-red";
    case "interactive":
      return "bg-accent/15 text-accent";
    case "neutral":
    default:
      return "bg-yellow/15 text-yellow";
  }
}

/** A projection value, colored by how it compares to a reference
 * (e.g. external baseline, or simply +/- around zero for a delta).
 * `value` is pre-formatted by the caller (e.g. "12.1", "+0.9"). */
export function ProjectionBadge({ value, tone = "interactive" }: { value: string; tone?: "positive" | "neutral" | "negative" | "interactive" }) {
  return <span className={`${BADGE_BASE} ${toneClasses(tone)}`}>{value}</span>;
}

/** Ownership percentage, colored by chalk-vs-leverage convention: high
 * ownership (chalk) reads neutral/amber, low ownership (leverage) reads
 * positive/green. Caller supplies the already-computed tone. */
export function OwnershipBadge({ percent, tone = "neutral" }: { percent: number | null; tone?: "positive" | "neutral" | "negative" }) {
  return <span className={`${BADGE_BASE} ${toneClasses(tone)}`}>{percent === null ? "--" : `${percent.toFixed(1)}%`}</span>;
}

/** Marks AI-derived content (research reasons, adjustment factors) --
 * purple is reserved exclusively for this. */
export function AIInsightBadge({ children }: { children: React.ReactNode }) {
  return <span className={`${BADGE_BASE} bg-purple/15 text-purple`}>✦ {children}</span>;
}

/** Generic research/status tag (elite_power, platoon_advantage, etc.). */
export function TagBadge({ children }: { children: React.ReactNode }) {
  return <span className={`${BADGE_BASE} bg-bg-panel-raised text-text-muted`}>{children}</span>;
}

/** Premium/membership badge -- gold is reserved exclusively for this. */
export function PremiumBadge({ children }: { children: React.ReactNode }) {
  return <span className={`${BADGE_BASE} bg-gold/15 text-gold`}>{children}</span>;
}
