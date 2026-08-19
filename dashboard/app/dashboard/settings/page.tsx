import Link from "next/link";

import { EnvironmentSectionToggles } from "@/components/environment/EnvironmentSectionToggles";
import { MockModeToggle } from "@/components/MockModeToggle";
import { PageHeader } from "@/components/ui/Header";
import { requireAdmin } from "@/lib/auth/guards";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { getMockModeEnabled } from "@/lib/mockMode";

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
 * for the documented, non-network-touching reason why.
 *
 * Milestone 29: admin-only. Everything on this page (DFS/external-
 * projection provider status, Mock Mode, Import Projections, Game
 * Environment provider status) is backend data-source configuration,
 * not a member account preference (see /account for that) -- gated here
 * the same way every /admin/* route is (requireAdmin() redirects a
 * non-admin to /dashboard), and the Settings link is removed from the
 * member Sidebar (components/Sidebar.tsx) so it's never dangled in
 * front of a member who'd just get redirected. */
export default async function SettingsPage() {
  await requireAdmin();
  const date = getTodayChicagoDate();
  const [status, environmentStatus, mockModeEnabled] = await Promise.all([
    getExternalProjectionsStatus(date),
    getGameEnvironmentStatus(date),
    getMockModeEnabled(),
  ]);

  if ("error" in status) {
    return (
      <div>
        <PageHeader title="Settings" />
        <div className="rounded-[var(--radius-control)] border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{status.error}</div>
      </div>
    );
  }

  const { provider, baseline, adjusted } = status;
  const isBlueCollar = provider.provider_key === "bluecollar" || provider.configured_source === "unconfigured";
  const isConnected = provider.is_configured && !provider.is_mock;
  const isMock = provider.is_mock === true && provider.is_configured;

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Provider configuration is read from server-side environment variables only -- nothing here can set or reveal a credential."
      />

      <div className="mb-4 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">DFS Salary Provider</h2>
        <p className="mb-3 text-xs text-text-faint">
          Priority: real uploaded DraftKings CSV → CSV-imported projection pool → Mock Mode (only if enabled below).
          Mock is never used silently.
        </p>
        <MockModeToggle initialEnabled={mockModeEnabled} />
      </div>

      <div className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
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

      <div className="mt-4 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">External Data</h2>
        <div className="flex items-center justify-between rounded border border-border-subtle bg-bg-panel-raised px-4 py-3">
          <div>
            <div className="text-sm font-medium text-text">Import Projections</div>
            <p className="mt-0.5 text-xs text-text-faint">
              Upload a projection CSV from BlueCollar, FantasyCruncher, SaberSim, or any other provider as an immutable
              baseline snapshot.
            </p>
          </div>
          <Link
            href="/dashboard/import"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-control)] bg-accent px-3.5 py-2 text-xs font-semibold text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            Import Projections
          </Link>
        </div>
      </div>

      <div className="mt-4 rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">Game Environment</h2>

        {"error" in environmentStatus ? (
          <div className="rounded-[var(--radius-control)] border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">
            {environmentStatus.error}
          </div>
        ) : (
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(
              [
                ["Weather", environmentStatus.providers.weather],
                ["Vegas", environmentStatus.providers.vegas],
                ["Umpire", environmentStatus.providers.umpire],
                ["Bullpen", environmentStatus.providers.bullpen],
              ] as const
            ).map(([label, p]) => (
              <div key={label} className="rounded border border-border-subtle bg-bg-panel-raised p-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-medium text-text">{label}</span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wide ${p.is_mock ? "text-yellow" : p.provider_name.startsWith("No ") ? "text-text-faint" : "text-green"}`}>
                    {p.is_mock ? "MOCK" : p.provider_name.startsWith("No ") ? "UNCONFIGURED" : "CONNECTED"}
                  </span>
                </div>
                <div className="text-[11px] text-text-faint">{p.provider_name}</div>
              </div>
            ))}
          </div>
        )}

        <p className="mb-2 text-xs text-text-faint">
          Section visibility on the Game Environment page and detail drawer -- a display preference only, saved in this
          browser. It never changes which providers the engine calls above.
        </p>
        <EnvironmentSectionToggles />
      </div>
    </div>
  );
}
