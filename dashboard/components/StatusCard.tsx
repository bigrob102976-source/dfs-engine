import type { ArtifactStatus } from "@/lib/types";

const STATE_STYLES: Record<ArtifactStatus["state"], { dot: string; label: string; text: string }> = {
  ready: { dot: "bg-green", label: "READY", text: "text-green" },
  missing: { dot: "bg-red", label: "MISSING", text: "text-red" },
  outdated: { dot: "bg-yellow", label: "OUTDATED", text: "text-yellow" },
};

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function StatusCard({ status }: { status: ArtifactStatus }) {
  const style = STATE_STYLES[status.state];
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-bg-panel p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{status.label}</span>
        <span className={`h-2 w-2 rounded-full ${style.dot}`} />
      </div>
      <span className={`text-sm font-semibold ${style.text}`}>{style.label}</span>
      {status.state === "ready" || status.state === "outdated" ? (
        <span className="text-xs text-text-faint">
          Generated: {formatTimestamp(status.generatedAtLocal ?? status.generatedAtUtc)}
        </span>
      ) : (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-text-faint">{status.detail ?? "Not generated yet."}</span>
          {status.helpCommand && (
            <code className="rounded bg-bg-panel-raised px-2 py-1 font-mono text-[11px] text-text-muted">
              {status.helpCommand}
            </code>
          )}
        </div>
      )}
    </div>
  );
}
