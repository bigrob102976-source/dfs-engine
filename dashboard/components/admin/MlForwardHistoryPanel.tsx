"use client";

import { useEffect, useState } from "react";

import { DataCard } from "@/components/ui/Card";

interface SourceMetricsRow {
  source: string;
  shared_sample_n: number;
  mae: number | null;
  rmse: number | null;
  pearson: number | null;
  spearman: number | null;
}

interface WindowResult {
  dates: string[];
  pitchers: { source_metrics: SourceMetricsRow[] };
  hitters: { source_metrics: SourceMetricsRow[] };
  combined: { source_metrics: SourceMetricsRow[] };
}

interface ForwardHistory {
  total_slates_completed: number;
  early_sample: boolean;
  early_sample_warning: string | null;
  windows: Record<string, WindowResult>;
}

function fmt(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}

const WINDOW_ORDER = ["1", "3", "5", "10", "all"];

/** Milestone 32.5 -- cumulative forward-history windows (1/3/5/10/all
 * completed slates), fetched from /api/admin/ml-forward-results/history
 * (which shells out to evaluation/ml_forward_history.py -- the pooled
 * Pearson/Spearman/MAE/RMSE math lives there, never reimplemented in
 * TypeScript). Never claims a model is "best" -- see the EARLY SAMPLE
 * banner, shown until at least 5 completed slates exist. */
export function MlForwardHistoryPanel() {
  const [history, setHistory] = useState<ForwardHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [window, setWindow] = useState("all");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/admin/ml-forward-results/history")
      .then((res) => res.json())
      .then((body) => {
        if (cancelled) return;
        if (body.error) {
          setError(body.error);
        } else {
          setHistory(body.history);
          const available = Object.keys(body.history?.windows ?? {});
          if (available.length > 0 && !available.includes("all")) setWindow(available[available.length - 1]);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load forward history.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <DataCard title="Cumulative Forward History">
        <p className="text-xs text-text-faint">Loading...</p>
      </DataCard>
    );
  }
  if (error || !history) {
    return (
      <DataCard title="Cumulative Forward History">
        <p className="text-xs text-red">{error ?? "No history available."}</p>
      </DataCard>
    );
  }

  const availableWindows = WINDOW_ORDER.filter((w) => history.windows[w]);
  const activeWindow = history.windows[window] ?? history.windows[availableWindows[availableWindows.length - 1]];

  return (
    <DataCard title="Cumulative Forward History">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-text-faint">{history.total_slates_completed} slate(s) completed</span>
        {history.early_sample && (
          <span className="rounded bg-yellow/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-yellow">{history.early_sample_warning}</span>
        )}
      </div>

      {availableWindows.length === 0 ? (
        <p className="text-xs text-text-faint">No completed slates yet -- run Collect Results once a slate is final.</p>
      ) : (
        <>
          <div className="mb-3 flex gap-1">
            {availableWindows.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setWindow(w)}
                className={`rounded px-2 py-1 text-[11px] font-medium ${window === w ? "bg-accent-dim text-text" : "bg-bg-panel-raised text-text-faint"}`}
              >
                {w === "all" ? "All" : `Last ${w}`}
              </button>
            ))}
          </div>
          {activeWindow && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {(["pitchers", "hitters", "combined"] as const).map((key) => (
                <div key={key}>
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint capitalize">{key}</h4>
                  {activeWindow[key].source_metrics.length === 0 ? (
                    <p className="text-[11px] text-text-faint">No data.</p>
                  ) : (
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="border-b border-border-subtle text-left uppercase tracking-wide text-text-faint">
                          <th className="px-1 py-1">Source</th>
                          <th className="px-1 py-1 text-right">N</th>
                          <th className="px-1 py-1 text-right">MAE</th>
                          <th className="px-1 py-1 text-right">RMSE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeWindow[key].source_metrics.map((row) => (
                          <tr key={row.source} className={`border-b border-border-subtle/50 ${row.source === "big_money_ml" ? "bg-purple/10" : ""}`}>
                            <td className="px-1 py-1">{row.source === "big_money_ml" ? "ML" : row.source}</td>
                            <td className="px-1 py-1 text-right">{row.shared_sample_n}</td>
                            <td className="px-1 py-1 text-right">{fmt(row.mae)}</td>
                            <td className="px-1 py-1 text-right">{fmt(row.rmse)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </DataCard>
  );
}
