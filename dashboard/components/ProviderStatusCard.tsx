import type { RunSummary, StepResult } from "@/lib/orchestrator/types";

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  return d.toLocaleString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

/** "DFS DATA PROVIDER" status card. Reflects the outcome of the most
 * recent refresh's DFS Salaries step -- never guesses at connectivity
 * before a refresh has actually checked, so it can't claim NOT CONNECTED
 * (or Connected) without having actually asked the configured provider. */
export function ProviderStatusCard({ summary, dfsStep }: { summary: RunSummary | null; dfsStep: StepResult | null }) {
  if (!dfsStep) {
    return (
      <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
        <div className="text-[11px] uppercase tracking-wide text-text-muted">DFS Data Provider</div>
        <div className="mt-1 text-sm text-text-faint">Not checked yet -- click Refresh Today&apos;s Slate.</div>
      </div>
    );
  }

  const connected = dfsStep.status === "ready" && !!summary?.providerName;

  return (
    <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
      <div className="text-[11px] uppercase tracking-wide text-text-muted">DFS Data Provider</div>
      {connected ? (
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="text-green">Provider: Connected ({summary!.providerName})</span>
          {summary!.isMock && (
            <span className="rounded bg-yellow/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-yellow">
              DEV / MOCK DATA
            </span>
          )}
          <span className="text-text">Slate: {summary!.selectedSlateId ?? "--"}</span>
          <span className="text-text">Players: {summary!.dkEntries ?? "--"}</span>
          <span className="text-text-faint">Updated: {formatTime(dfsStep.finishedAt)}</span>
        </div>
      ) : (
        <div className="mt-1 text-sm">
          <span className="text-red">Provider: NOT CONNECTED</span>
          <div className="mt-0.5 text-xs text-text-faint">
            {dfsStep.message ?? "Configure DFS_SALARY_PROVIDER (and DFS_PROVIDER_API_KEY if required) to enable automatic salary ingestion."}
          </div>
        </div>
      )}
    </div>
  );
}
