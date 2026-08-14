"use client";

import { AIInsightBadge, TagBadge } from "@/components/ui/Badge";
import { Drawer } from "@/components/ui/Drawer";
import { SectionHeader } from "@/components/ui/Header";
import type { PlayerRow } from "@/lib/types";

function fmt(value: unknown, digits = 1): string {
  if (value === null || value === undefined) return "--";
  if (typeof value === "number") return value.toFixed(digits);
  return String(value);
}

function MetricBlock({ title, data }: { title: string; data: Record<string, unknown> | undefined }) {
  if (!data || Object.keys(data).length === 0) return null;
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined && typeof v !== "object");
  if (entries.length === 0) return null;
  return (
    <div className="mb-3">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-faint">{title}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 text-text-muted">
            <span className="truncate">{k.replace(/_/g, " ")}</span>
            <span className="text-text">{fmt(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Slide-out PROJECTION/RESEARCH detail for one player -- sections
 * follow the design system's taxonomy (Overview / Research / Recent
 * Form / Ownership / AI Notes), each rendered only when the underlying
 * data actually exists (no fabricated Statcast/Weather/Vegas sections
 * -- those data sources don't have a dedicated per-player surface yet,
 * see the Weather/Vegas placeholder pages). */
export function PlayerDetailPanel({ row, onClose }: { row: PlayerRow | null; onClose: () => void }) {
  if (!row) return null;
  const snapshot = row.raw.snapshot as Record<string, unknown>;

  return (
    <Drawer onClose={onClose} ariaLabel={`${row.name} player detail`}>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-base font-semibold text-text">{row.name}</div>
          <div className="text-xs text-text-faint">
            {row.team} {row.opponent ? `vs ${row.opponent}` : ""} &middot; {row.playerType}
            {row.position ? ` · ${row.position}` : ""}
            {row.battingOrder ? ` · batting ${row.battingOrder}` : ""}
          </div>
        </div>
        <button onClick={onClose} className="text-text-faint hover:text-text" aria-label="Close">
          ✕
        </button>
      </div>

      <SectionHeader title="Overview" />
      <div className="mb-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Projection</div>
          <div className="text-sm font-semibold text-text">{fmt(row.projection)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Ceiling</div>
          <div className="text-sm font-semibold text-text">{fmt(row.ceiling)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Floor</div>
          <div className="text-sm font-semibold text-text">{fmt(row.floor)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Ownership</div>
          <div className="text-sm font-semibold text-yellow">{row.ownership !== null ? `${fmt(row.ownership)}%` : "--"}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Leverage</div>
          <div className={`text-sm font-semibold ${row.leverage !== null && row.leverage >= 0 ? "text-green" : "text-text"}`}>{fmt(row.leverage)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Confidence</div>
          <div className="text-sm font-semibold text-text">{fmt(row.confidence)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Risk</div>
          <div className="text-sm font-semibold text-text">{fmt(row.risk)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Overall</div>
          <div className="text-sm font-semibold text-text">{fmt(row.overall)}</div>
        </div>
        <div className="rounded-[var(--radius-control)] bg-bg-panel-raised p-2">
          <div className="text-[10px] text-text-faint">Salary</div>
          <div className="text-sm font-semibold text-text">{row.salary ?? "--"}</div>
        </div>
      </div>

      {row.tags.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1">
          {row.tags.map((t) => (
            <TagBadge key={t}>{t}</TagBadge>
          ))}
        </div>
      )}

      {row.reasons.length > 0 && (
        <div className="mb-4">
          <SectionHeader title="AI Notes" />
          <div className="flex flex-col gap-1.5">
            {row.reasons.map((r, i) => (
              <AIInsightBadge key={i}>{r}</AIInsightBadge>
            ))}
          </div>
        </div>
      )}

      {Boolean(snapshot.season_metrics || snapshot.trend_metrics) && (
        <div>
          <SectionHeader title="Research" />
          <MetricBlock title="Season Metrics" data={snapshot.season_metrics as Record<string, unknown>} />
          <MetricBlock title="Trend Metrics" data={snapshot.trend_metrics as Record<string, unknown>} />
        </div>
      )}

      <MetricBlock title="Recent Form" data={snapshot.recent_metrics as Record<string, unknown>} />

      {row.raw.ownership && (
        <MetricBlock title="Ownership Feature Breakdown" data={row.raw.ownership.feature_breakdown} />
      )}

      <div className="mt-4 border-t border-border-subtle pt-3 text-[11px] text-text-faint">
        Prediction history: only the latest snapshot is currently retained per slate. Multi-snapshot history
        (morning vs. pre-lock runs) will render here once more than one is available for this slate date.
      </div>
    </Drawer>
  );
}
