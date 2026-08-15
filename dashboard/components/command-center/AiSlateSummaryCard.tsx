import { AIInsightBadge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/Header";

/** LEFT COLUMN: the deterministic AI Slate Summary. `bullets` comes from
 * lib/commandCenter.ts::buildSlateAiSummary -- template text over
 * already-computed thresholds, no LLM, same discipline as
 * research/game_environment/summary.py and
 * lib/vegasIntelligence.ts::buildVegasAiSummary. */
export function AiSlateSummaryCard({ bullets }: { bullets: string[] }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
      <SectionHeader title="AI Slate Summary" />
      <div className="flex flex-col gap-1.5">
        {bullets.map((b, i) => (
          <AIInsightBadge key={i}>{b}</AIInsightBadge>
        ))}
      </div>
    </div>
  );
}
