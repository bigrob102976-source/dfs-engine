import type { SlateRankingBadge } from "@/lib/commandCenter";

const BADGE_BASE = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide";

const TONE_CLASSES: Record<SlateRankingBadge["tone"], string> = {
  positive: "bg-green/15 text-green",
  negative: "bg-red/15 text-red",
  interactive: "bg-accent/15 text-accent",
  neutral: "bg-yellow/15 text-yellow",
};

/** Mirrors components/vegas/VegasBadgeRow.tsx's rendering exactly, but
 * kept as its own small component rather than importing that one --
 * Slate Rankings badges add two keys (Wind Out, Leverage) Vegas
 * Intelligence's own badge type doesn't have, and that file must not be
 * modified to widen its prop type. */
export function SlateRankingBadgeRow({ badges }: { badges: SlateRankingBadge[] }) {
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
