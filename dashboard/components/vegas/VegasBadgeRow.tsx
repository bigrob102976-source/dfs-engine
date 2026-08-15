import type { VegasBadge } from "@/lib/vegasIntelligence";

const BADGE_BASE = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide";

const TONE_CLASSES: Record<VegasBadge["tone"], string> = {
  positive: "bg-green/15 text-green",
  negative: "bg-red/15 text-red",
  interactive: "bg-accent/15 text-accent",
  neutral: "bg-yellow/15 text-yellow",
};

/** Renders the deterministic badge set from lib/vegasIntelligence.ts's
 * deriveVegasBadges() -- same six-color badge system as
 * components/ui/Badge.tsx (this lives alongside it rather than in it
 * since these tones are keyed by VegasBadgeKey, a Vegas-only concept). */
export function VegasBadgeRow({ badges }: { badges: VegasBadge[] }) {
  if (badges.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((b) => (
        <span key={b.key} className={`${BADGE_BASE} ${TONE_CLASSES[b.tone]}`}>
          {b.label}
        </span>
      ))}
    </div>
  );
}
