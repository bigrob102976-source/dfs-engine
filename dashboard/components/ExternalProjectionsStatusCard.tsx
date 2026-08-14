"use client";

import { useEffect, useState } from "react";

interface ExternalProjectionsStatus {
  slate_date: string;
  provider: {
    configured_source: "unconfigured" | "explicit" | "unknown";
    reason: string | null;
    provider_key: string | null;
    provider_name: string | null;
    is_mock: boolean | null;
    is_configured: boolean;
  };
  baseline: { exists: boolean; provider_name: string | null; is_mock: boolean | null; retrieved_at: string | null; player_count: number | null };
  adjusted: { exists: boolean; generated_at: string | null; record_count: number | null; adjustment_model_version: string | null };
}

/** "External Projection Provider" status card for the main dashboard
 * (Milestone 17). Renders BlueCollar's disabled-until-credentialed
 * state as a plain, calm "WAITING FOR API ACCESS" -- never an error --
 * and always shows Big Money Independent as READY, since the optimizer
 * never depends on an external provider to function. When the mock
 * provider is active it is labeled distinctly (MOCK) so it can never be
 * mistaken for real BlueCollar data. */
export function ExternalProjectionsStatusCard() {
  const [status, setStatus] = useState<ExternalProjectionsStatus | null>(null);

  useEffect(() => {
    fetch("/api/external-projections/status")
      .then((res) => res.json())
      .then((data) => setStatus(data.provider ? data : null))
      .catch(() => setStatus(null));
  }, []);

  const provider = status?.provider;
  const isBlueCollarWaiting = !provider || provider.configured_source === "unconfigured" || (provider.provider_key === "bluecollar" && !provider.is_configured);
  const isMockReady = provider?.is_mock === true && provider?.is_configured === true;

  return (
    <div className="rounded-lg border border-border bg-bg-panel p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">External Projection Provider</h2>

      <div className="flex flex-col gap-2 text-sm">
        {isMockReady ? (
          <div className="flex items-center justify-between rounded border border-border-subtle bg-bg-panel-raised px-3 py-2">
            <div>
              <div className="font-medium text-text">MOCK EXTERNAL PROJECTIONS</div>
              {status?.baseline.exists && (
                <div className="text-[11px] text-text-faint">
                  Baseline: {status.baseline.player_count ?? 0} players
                  {status.adjusted.exists ? ` · Adjusted: ${status.adjusted.record_count ?? 0} records` : ""}
                </div>
              )}
            </div>
            <span className="text-xs font-semibold uppercase tracking-wide text-green">READY</span>
          </div>
        ) : (
          <div className="flex items-center justify-between rounded border border-border-subtle bg-bg-panel-raised px-3 py-2">
            <div className="font-medium text-text">BlueCollar DFS</div>
            <span className="text-xs font-semibold uppercase tracking-wide text-yellow">{isBlueCollarWaiting ? "WAITING FOR API ACCESS" : "NOT CONFIGURED"}</span>
          </div>
        )}

        <div className="flex items-center justify-between rounded border border-border-subtle bg-bg-panel-raised px-3 py-2">
          <div className="font-medium text-text">Big Money Independent</div>
          <span className="text-xs font-semibold uppercase tracking-wide text-green">READY</span>
        </div>
      </div>
    </div>
  );
}
