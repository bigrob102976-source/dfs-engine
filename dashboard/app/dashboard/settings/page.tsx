import { getTodayChicagoDate } from "@/lib/currentDate";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";

export const dynamic = "force-dynamic";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Settings / Provider section (Milestone 17): shows exactly what
 * connecting a real external projection provider requires, without ever
 * exposing a credential value. BlueCollar is always shown as "Waiting
 * for API key" today -- see external_projections/bluecollar_provider.py
 * for the documented, non-network-touching reason why. */
export default async function SettingsPage() {
  const date = getTodayChicagoDate();
  const status = await getExternalProjectionsStatus(date);

  if ("error" in status) {
    return (
      <div>
        <h1 className="mb-4 text-lg font-semibold text-text">Settings</h1>
        <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{status.error}</div>
      </div>
    );
  }

  const { provider, baseline, adjusted } = status;
  const isBlueCollar = provider.provider_key === "bluecollar" || provider.configured_source === "unconfigured";
  const isConnected = provider.is_configured && !provider.is_mock;
  const isMock = provider.is_mock === true && provider.is_configured;

  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold text-text">Settings</h1>
      <p className="mb-4 text-xs text-text-faint">Provider configuration is read from server-side environment variables only -- nothing here can set or reveal a credential.</p>

      <div className="rounded-lg border border-border bg-bg-panel p-4">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">External Projections</h2>

        <div className="rounded border border-border-subtle bg-bg-panel-raised p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-text">{isMock ? "MOCK EXTERNAL PROJECTIONS" : "BlueCollar DFS"}</span>
            <span className={`text-xs font-semibold uppercase tracking-wide ${isConnected || isMock ? "text-green" : "text-yellow"}`}>
              {isMock ? "READY (MOCK)" : isConnected ? "Connected" : "Waiting for API key"}
            </span>
          </div>

          {isBlueCollar && !isMock && (
            <p className="text-xs text-text-faint">
              BlueCollar DFS is not connected yet -- official API documentation and credentials have not been
              provided. Set <code className="text-text-muted">EXTERNAL_PROJECTION_PROVIDER=bluecollar</code>,{" "}
              <code className="text-text-muted">BLUECOLLAR_API_KEY</code>, and{" "}
              <code className="text-text-muted">BLUECOLLAR_API_BASE_URL</code> once they exist. The app remains
              fully usable without it -- Big Money Independent projections always work.
            </p>
          )}

          {(isConnected || isMock) && (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-text-faint">Status</dt>
              <dd className="text-text">{isMock ? "Ready (mock data)" : "Connected"}</dd>
              <dt className="text-text-faint">Last Updated</dt>
              <dd className="text-text">{formatTimestamp(baseline.retrieved_at)}</dd>
              <dt className="text-text-faint">Slate</dt>
              <dd className="text-text">{baseline.exists ? date : "--"}</dd>
              <dt className="text-text-faint">Players</dt>
              <dd className="text-text">{baseline.player_count ?? "--"}</dd>
              {adjusted.exists && (
                <>
                  <dt className="text-text-faint">Adjustment Model</dt>
                  <dd className="text-text">{adjusted.adjustment_model_version ?? "--"}</dd>
                  <dt className="text-text-faint">Adjusted Records</dt>
                  <dd className="text-text">{adjusted.record_count ?? "--"}</dd>
                </>
              )}
            </dl>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between rounded border border-border-subtle bg-bg-panel-raised px-4 py-3">
          <span className="text-sm font-medium text-text">Big Money Independent</span>
          <span className="text-xs font-semibold uppercase tracking-wide text-green">READY</span>
        </div>
      </div>
    </div>
  );
}
