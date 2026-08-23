import { DataCard } from "@/components/ui/Card";
import type { SlateCompletionStage, SlateReadinessSummary } from "@/lib/slateReadiness";

const STAGE_LABEL: Record<SlateCompletionStage, string> = {
  EARLY: "Early",
  PARTIAL_LINEUPS: "Partial Lineups",
  MOSTLY_READY: "Mostly Ready",
  READY: "Ready",
  LOCKED: "Locked",
  IN_PROGRESS: "In Progress",
  FINAL: "Final",
};

const STAGE_TONE: Record<SlateCompletionStage, string> = {
  EARLY: "bg-text-faint/15 text-text-faint",
  PARTIAL_LINEUPS: "bg-yellow/15 text-yellow",
  MOSTLY_READY: "bg-yellow/15 text-yellow",
  READY: "bg-green/15 text-green",
  LOCKED: "bg-accent/15 text-accent",
  IN_PROGRESS: "bg-accent/15 text-accent",
  FINAL: "bg-text-faint/15 text-text-faint",
};

function row(label: string, value: string) {
  return (
    <>
      <dt className="text-text-faint">{label}</dt>
      <dd className="text-right font-semibold text-text">{value}</dd>
    </>
  );
}

/** M32.7: makes the whole day's slate readiness legible at a glance --
 * every number here traces directly to an already-built snapshot/match
 * report (see lib/slateReadiness.ts); nothing is recomputed here. */
export function SlateReadinessCard({ readiness, stage }: { readiness: SlateReadinessSummary; stage: SlateCompletionStage }) {
  return (
    <DataCard
      title="Slate Readiness"
      action={<span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STAGE_TONE[stage]}`}>{STAGE_LABEL[stage]}</span>}
    >
      <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
        {row("DK Players", String(readiness.dkPlayers))}
        {row("Identity Resolved", `${readiness.identityResolved} / ${readiness.dkPlayers}`)}
        {row("Starting Pitchers", `${readiness.startingPitchers.covered} / ${readiness.startingPitchers.eligible}`)}
        {row("Lineups Confirmed", `${readiness.lineupsConfirmed.covered} / ${readiness.lineupsConfirmed.eligible} teams`)}
        {row("BlueCollar Usable", String(readiness.blueCollarUsable))}
        {row("Native Eligible", `${readiness.nativeEligible.covered} / ${readiness.nativeEligible.eligible}`)}
        {row("AI Eligible", `${readiness.aiEligible.covered} / ${readiness.aiEligible.eligible}`)}
        {row("Big Money ML Eligible", `${readiness.mlEligible.covered} / ${readiness.mlEligible.eligible}`)}
        <dt className="font-semibold text-text-faint">Optimizer Eligible</dt>
        <dd className="text-right font-semibold text-green">{readiness.optimizerEligible}</dd>
      </dl>
    </DataCard>
  );
}
