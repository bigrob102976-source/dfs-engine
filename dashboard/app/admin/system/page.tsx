import { DataCard, MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { computeDbStats } from "@/lib/db/systemStats";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { getMockModeEnabled } from "@/lib/mockMode";

export const dynamic = "force-dynamic";

/** Composes EXISTING, already-real status functions (mock mode, external
 * projections, game environment providers) the same way Settings does,
 * plus live counts from the membership DB -- never a second, parallel
 * definition of "is this connected." No READY is faked here. */
export default async function AdminSystemPage() {
  const date = getTodayChicagoDate();
  const [mockModeEnabled, externalStatus, environmentStatus] = await Promise.all([
    getMockModeEnabled(),
    getExternalProjectionsStatus(date),
    getGameEnvironmentStatus(date),
  ]);
  const dbStats = computeDbStats();

  return (
    <div>
      <PageHeader title="System Status" description="Live status of every provider and data store the app depends on." />

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Total Users" value={dbStats.totalUsers} />
        <MetricCard label="Active Sessions" value={dbStats.totalSessions} />
        <MetricCard label="Subscriptions" value={dbStats.totalSubscriptions} />
        <MetricCard label="Audit Log Entries" value={dbStats.totalAuditLogEntries} />
      </div>

      <DataCard title="DFS Salary Provider" className="mb-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-text">Mock Mode</span>
          <span className={`text-xs font-semibold uppercase tracking-wide ${mockModeEnabled ? "text-yellow" : "text-green"}`}>
            {mockModeEnabled ? "ENABLED" : "DISABLED"}
          </span>
        </div>
      </DataCard>

      <DataCard title="External Projections" className="mb-4">
        {"error" in externalStatus ? (
          <p className="text-xs text-red">{externalStatus.error}</p>
        ) : (
          <dl className="grid grid-cols-2 gap-y-2 text-xs">
            <dt className="text-text-faint">Provider</dt>
            <dd className="text-right text-text">{externalStatus.provider.provider_name ?? "Not configured"}</dd>
            <dt className="text-text-faint">Configured</dt>
            <dd className="text-right text-text">{externalStatus.provider.is_configured ? "Yes" : "No"}</dd>
            <dt className="text-text-faint">Baseline Loaded</dt>
            <dd className="text-right text-text">{externalStatus.baseline.exists ? "Yes" : "No"}</dd>
          </dl>
        )}
      </DataCard>

      <DataCard title="Game Environment Providers">
        {"error" in environmentStatus ? (
          <p className="text-xs text-red">{environmentStatus.error}</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
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
      </DataCard>
    </div>
  );
}
