"use client";

import { useState } from "react";

/** Milestone 19: the ONLY way to turn on mock DFS salary data. OFF by
 * default -- there is no automatic fallback anymore (see
 * dfs/providers/config.py). Every page shows a DEV MODE banner while
 * this is on (see app/dashboard/layout.tsx). */
export function MockModeToggle({ initialEnabled }: { initialEnabled: boolean }) {
  const [enabled, setEnabled] = useState(initialEnabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleToggle() {
    const next = !enabled;
    setSaving(true);
    setError(null);
    fetch("/api/settings/mock-mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: next }),
    })
      .then((res) => res.json())
      .then((data) => {
        setSaving(false);
        if (data.error) {
          setError(data.error);
          return;
        }
        setEnabled(Boolean(data.enabled));
      })
      .catch(() => {
        setSaving(false);
        setError("Failed to update Mock Mode.");
      });
  }

  return (
    <div className="rounded border border-border-subtle bg-bg-panel-raised p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-text">Mock Mode</div>
          <p className="mt-0.5 text-xs text-text-faint">
            Development/testing only. When ON, the DFS salary provider falls back to mock data if no real
            DraftKings CSV or CSV-imported pool is available -- <span className="text-yellow">DEV MODE</span> shows on
            every page while enabled.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={handleToggle}
          disabled={saving}
          className={`ml-4 flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-150 disabled:opacity-50 ${
            enabled ? "bg-yellow" : "bg-bg-panel"
          }`}
        >
          <span className={`h-5 w-5 rounded-full bg-white shadow transition-transform duration-150 ${enabled ? "translate-x-5" : "translate-x-0.5"}`} />
        </button>
      </div>
      <div className="mt-2 text-xs font-semibold uppercase tracking-wide">
        {enabled ? <span className="text-yellow">DEV MODE -- Mock Mode is ON</span> : <span className="text-green">OFF (default)</span>}
      </div>
      {error && <div className="mt-1 text-xs text-red">{error}</div>}
    </div>
  );
}
