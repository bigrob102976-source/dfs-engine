import { DataCard, MetricCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Header";
import { getStripeConfigStatus } from "@/lib/billing/stripeConfig";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { countWebhookEventsByStatus, getLastSuccessfulWebhookEvent, listRecentWebhookEvents } from "@/lib/db/stripeWebhookEvents";
import { computeDbStats } from "@/lib/db/systemStats";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";
import { getFantasyProsStatus } from "@/lib/fantasyProsStatus";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { getMlHitterShadowStatus, getMlShadowStatus } from "@/lib/mlShadowStatus";
import { getMockModeEnabled } from "@/lib/mockMode";
import { getDatabaseReadiness, getJobQueueReadiness, getObjectStorageReadiness, getWorkerReadiness } from "@/lib/systemReadiness";

export const dynamic = "force-dynamic";

function fmtDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "--"
    : d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Composes EXISTING, already-real status functions (mock mode, external
 * projections, game environment providers) the same way Settings does,
 * plus live counts from the membership DB -- never a second, parallel
 * definition of "is this connected." No READY is faked here. */
export default async function AdminSystemPage() {
  const date = getTodayChicagoDate();
  const [
    mockModeEnabled,
    externalStatus,
    fantasyProsStatus,
    environmentStatus,
    databaseReadiness,
    objectStorageReadiness,
    jobQueueReadiness,
    workerReadiness,
    dbStats,
    webhookCounts,
    lastSuccessfulWebhook,
    recentFailedWebhooksAll,
  ] = await Promise.all([
    getMockModeEnabled(),
    getExternalProjectionsStatus(date),
    getFantasyProsStatus(date, null),
    getGameEnvironmentStatus(date),
    getDatabaseReadiness(),
    getObjectStorageReadiness(),
    getJobQueueReadiness(),
    getWorkerReadiness(),
    computeDbStats(),
    countWebhookEventsByStatus(),
    getLastSuccessfulWebhookEvent(),
    listRecentWebhookEvents(50),
  ]);
  const mlShadowStatus = getMlShadowStatus(date);
  const mlHitterShadowStatus = getMlHitterShadowStatus(date);
  const stripeConfigStatus = getStripeConfigStatus();
  const recentFailedWebhooks = recentFailedWebhooksAll.filter((e) => e.status === "failed").slice(0, 5);

  return (
    <div>
      <PageHeader title="System Status" description="Live status of every provider and data store the app depends on." />

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Total Users" value={dbStats.totalUsers} />
        <MetricCard label="Active Sessions" value={dbStats.totalSessions} />
        <MetricCard label="Subscriptions" value={dbStats.totalSubscriptions} />
        <MetricCard label="Audit Log Entries" value={dbStats.totalAuditLogEntries} />
      </div>

      <DataCard title="Production Infrastructure" className="mb-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded border border-border-subtle bg-bg-panel-raised p-3" title={databaseReadiness.detail}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-text">Database</span>
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${databaseReadiness.status === "CONNECTED" ? "text-green" : "text-red"}`}>
                {databaseReadiness.status}
              </span>
            </div>
            <div className="text-[11px] text-text-faint">{databaseReadiness.kind === "postgres" ? "PostgreSQL" : "SQLite"}</div>
          </div>
          <div className="rounded border border-border-subtle bg-bg-panel-raised p-3" title={objectStorageReadiness.detail}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-text">Object Storage</span>
              <span
                className={`text-[10px] font-semibold uppercase tracking-wide ${
                  objectStorageReadiness.status === "CONNECTED" ? "text-green" : objectStorageReadiness.status === "NOT_CONFIGURED" ? "text-text-faint" : "text-red"
                }`}
              >
                {objectStorageReadiness.status.replace("_", " ")}
              </span>
            </div>
            <div className="text-[11px] text-text-faint">S3-compatible</div>
          </div>
          <div className="rounded border border-border-subtle bg-bg-panel-raised p-3" title={jobQueueReadiness.detail}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-text">Job Queue</span>
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${jobQueueReadiness.status === "CONNECTED" ? "text-green" : "text-red"}`}>
                {jobQueueReadiness.status}
              </span>
            </div>
            <div className="text-[11px] text-text-faint">
              {jobQueueReadiness.queuedCount ?? "--"} queued, {jobQueueReadiness.runningCount ?? "--"} running
            </div>
          </div>
          <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-text">Worker</span>
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${workerReadiness.status === "ONLINE" ? "text-green" : "text-text-faint"}`}>
                {workerReadiness.status}
              </span>
            </div>
            <div className="text-[11px] text-text-faint">{workerReadiness.workers.length} worker(s) seen</div>
          </div>
        </div>
      </DataCard>

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

      <DataCard title="FantasyPros" className="mb-4">
        {"error" in fantasyProsStatus ? (
          <p className="text-xs text-red">{fantasyProsStatus.error}</p>
        ) : (
          <>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm text-text">Status</span>
              <span
                className={`text-xs font-semibold uppercase tracking-wide ${
                  fantasyProsStatus.status === "AVAILABLE"
                    ? "text-green"
                    : fantasyProsStatus.status === "PARTIAL"
                      ? "text-yellow"
                      : "text-text-faint"
                }`}
              >
                {fantasyProsStatus.status === "NOT_CONFIGURED" && "FantasyPros: NOT CONFIGURED"}
                {fantasyProsStatus.status === "NO_SNAPSHOT" && "FantasyPros: NO SNAPSHOT"}
                {fantasyProsStatus.status === "AVAILABLE" &&
                  `FantasyPros: AVAILABLE -- ${fantasyProsStatus.matched_eligible_players}/${fantasyProsStatus.eligible_players} eligible players`}
                {fantasyProsStatus.status === "PARTIAL" &&
                  `FantasyPros: PARTIAL -- ${fantasyProsStatus.matched_eligible_players}/${fantasyProsStatus.eligible_players} eligible players`}
              </span>
            </div>
            <dl className="grid grid-cols-2 gap-y-2 text-xs">
              <dt className="text-text-faint">Configured</dt>
              <dd className="text-right text-text">{fantasyProsStatus.configured ? "Yes" : "No"}</dd>
              <dt className="text-text-faint">Snapshot Retrieved</dt>
              <dd className="text-right text-text">{fantasyProsStatus.retrieved_at ?? "--"}</dd>
              <dt className="text-text-faint">Hitters / Pitchers Returned</dt>
              <dd className="text-right text-text">
                {fantasyProsStatus.hitter_count ?? "--"} / {fantasyProsStatus.pitcher_count ?? "--"}
              </dd>
              {fantasyProsStatus.public_api_limited && (
                <>
                  <dt className="text-text-faint">API Tier</dt>
                  <dd className="text-right text-yellow">{fantasyProsStatus.api_tier ?? "free"} (public API limited)</dd>
                </>
              )}
            </dl>
            <p className="mt-2 text-[11px] text-text-faint">
              A live API failure during Process/Refresh appears in that run&apos;s errors, not here -- this card only reflects the last
              persisted snapshot. FantasyPros is a comparison + optional optimizer source; it never affects Native/AI or slate eligibility.
            </p>
          </>
        )}
      </DataCard>

      <DataCard title="Big Money ML (Shadow)" className="mb-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm text-text">Pitchers</span>
          <span
            className={`text-xs font-semibold ${
              mlShadowStatus.status === "READY" ? "text-green" : mlShadowStatus.status === "PARTIAL" ? "text-yellow" : "text-text-faint"
            }`}
          >
            {mlShadowStatus.status === "NO_SNAPSHOT" && "Big Money ML: NO SNAPSHOT"}
            {mlShadowStatus.status === "NO_ELIGIBLE_PITCHERS" && "Big Money ML: NO ELIGIBLE PITCHERS"}
            {mlShadowStatus.status === "READY" &&
              `Big Money ML / PITCHERS ${mlShadowStatus.ml_projections_generated}/${mlShadowStatus.ml_eligible_pitcher_count}`}
            {mlShadowStatus.status === "PARTIAL" &&
              `Big Money ML / PITCHERS ${mlShadowStatus.ml_projections_generated}/${mlShadowStatus.ml_eligible_pitcher_count} -- PARTIAL`}
          </span>
        </div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm text-text">Hitters</span>
          <span
            className={`text-xs font-semibold ${
              mlHitterShadowStatus.status === "READY" ? "text-green" : mlHitterShadowStatus.status === "PARTIAL" ? "text-yellow" : "text-text-faint"
            }`}
          >
            {mlHitterShadowStatus.status === "NO_SNAPSHOT" && "Big Money ML: NO SNAPSHOT"}
            {mlHitterShadowStatus.status === "NO_ELIGIBLE_HITTERS" && "Big Money ML: NO ELIGIBLE HITTERS"}
            {mlHitterShadowStatus.status === "READY" &&
              `Big Money ML / HITTERS ${mlHitterShadowStatus.ml_projections_generated}/${mlHitterShadowStatus.ml_eligible_hitter_count}`}
            {mlHitterShadowStatus.status === "PARTIAL" &&
              `Big Money ML / HITTERS ${mlHitterShadowStatus.ml_projections_generated}/${mlHitterShadowStatus.ml_eligible_hitter_count} -- PARTIAL`}
          </span>
        </div>
        <dl className="grid grid-cols-2 gap-y-2 text-xs">
          <dt className="text-text-faint">Model Version (Pitcher / Hitter)</dt>
          <dd className="text-right text-text">
            {mlShadowStatus.model_version ?? "--"} / {mlHitterShadowStatus.model_version ?? "--"}
          </dd>
          <dt className="text-text-faint">Generated At (Pitcher / Hitter)</dt>
          <dd className="text-right text-text">
            {fmtDateTime(mlShadowStatus.generated_at)} / {fmtDateTime(mlHitterShadowStatus.generated_at)}
          </dd>
        </dl>
        <p className="mt-2 text-[11px] text-text-faint">
          A feature-parity or model-load failure during Process/Refresh appears in that run&apos;s errors, not here (never blocks slate
          publication). Big Money ML is a SHADOW evaluation source; it never affects Native/AI, ownership, or the optimizer.
        </p>
      </DataCard>

      <DataCard title="Game Environment Providers" className="mb-4">
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

      <DataCard title="Stripe Webhooks">
        <dl className="mb-3 grid grid-cols-2 gap-y-2 text-xs">
          <dt className="text-text-faint">Stripe Configured</dt>
          <dd className="text-right text-text">{stripeConfigStatus.configured ? "Yes" : "No"}</dd>
          {!stripeConfigStatus.configured && !stripeConfigStatus.blocked && (
            <>
              <dt className="text-text-faint">Missing Configuration</dt>
              <dd className="text-right text-text">{stripeConfigStatus.missing.join(", ")}</dd>
            </>
          )}
          {stripeConfigStatus.blocked && (
            <>
              <dt className="text-text-faint">Blocked</dt>
              <dd className="text-right text-red">Live key rejected -- test mode only</dd>
            </>
          )}
          <dt className="text-text-faint">Processed</dt>
          <dd className="text-right text-green">{webhookCounts.processed}</dd>
          <dt className="text-text-faint">Failed</dt>
          <dd className="text-right text-red">{webhookCounts.failed}</dd>
          <dt className="text-text-faint">In Progress</dt>
          <dd className="text-right text-yellow">{webhookCounts.processing}</dd>
          <dt className="text-text-faint">Last Successful Webhook</dt>
          <dd className="text-right text-text">
            {lastSuccessfulWebhook ? `${lastSuccessfulWebhook.type} -- ${fmtDateTime(lastSuccessfulWebhook.processed_at)}` : "--"}
          </dd>
        </dl>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-text-faint">Recent Failed Webhooks</div>
          {recentFailedWebhooks.length === 0 ? (
            <p className="text-xs text-text-faint">No failed webhook deliveries recorded.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {recentFailedWebhooks.map((e) => (
                <li key={e.id} className="text-[11px] text-text-muted">
                  <span className="text-text-faint">{fmtDateTime(e.received_at)}</span> -- {e.type}: {e.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      </DataCard>
    </div>
  );
}
