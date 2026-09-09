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

// An UNKNOWN value (no dk_match_report_ document -- see
// lib/slateReadiness.ts) renders as a dimmed em dash, never as a number.
// It must not be possible to read "no data" as either 0 or full coverage.
const UNKNOWN = "—";

function row(label: string, value: string, unknown = false) {
  return (
    <>
      <dt className="text-text-faint">{label}</dt>
      <dd className={`text-right font-semibold ${unknown ? "text-text-faint" : "text-text"}`} title={unknown ? "No DK match report available for this slate yet -- this value is unknown, not zero." : undefined}>
        {value}
      </dd>
    </>
  );
}

function count(value: number | null): string {
  return value === null ? UNKNOWN : String(value);
}

function ratio(covered: number | null, eligible: number, suffix = ""): string {
  return `${count(covered)} / ${eligible}${suffix}`;
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
        {row("DK Players", count(readiness.dkPlayers), readiness.dkPlayers === null)}
        {row("Identity Resolved", `${count(readiness.identityResolved)} / ${count(readiness.dkPlayers)}`, readiness.identityResolved === null)}
        {row("Starting Pitchers", ratio(readiness.startingPitchers.covered, readiness.startingPitchers.eligible), readiness.startingPitchers.covered === null)}
        {row("Lineups Confirmed", ratio(readiness.lineupsConfirmed.covered, readiness.lineupsConfirmed.eligible, " teams"), readiness.lineupsConfirmed.covered === null)}
        {row("BlueCollar Usable", String(readiness.blueCollarUsable))}
        {row("Native Eligible", ratio(readiness.nativeEligible.covered, readiness.nativeEligible.eligible))}
        {row("AI Eligible", ratio(readiness.aiEligible.covered, readiness.aiEligible.eligible))}
        {row("Big Money ML Eligible", ratio(readiness.mlEligible.covered, readiness.mlEligible.eligible))}
        <dt className="font-semibold text-text-faint">Optimizer Eligible</dt>
        <dd className={`text-right font-semibold ${readiness.optimizerEligible === null ? "text-text-faint" : "text-green"}`}>
          {count(readiness.optimizerEligible)}
        </dd>
      </dl>
      {!readiness.matchReportAvailable && (
        <p className="mt-2 text-[11px] leading-snug text-text-faint">
          {UNKNOWN} No DK match report for this slate yet -- those values are unknown, not zero.
        </p>
      )}
    </DataCard>
  );
}
