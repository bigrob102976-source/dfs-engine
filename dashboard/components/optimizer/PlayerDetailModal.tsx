"use client";

import { AIInsightBadge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

/** PROJECTION COMPARISON detail (Milestone 17): clearly distinguishes
 * provider-derived data (External Baseline) from Big Money's own
 * analysis (Independent, Adjusted) for one player. Renders a plain "no
 * external data" message rather than an error when no baseline/adjusted
 * snapshot covers this player yet. */
export function PlayerDetailModal({ player, onClose }: { player: PoolPlayerRow; onClose: () => void }) {
  const hasComparison = player.externalProjection !== null || player.adjustedProjection !== null;

  return (
    <Modal onClose={onClose} ariaLabel={`${player.name} projection comparison`}>
      <div className="mb-1 flex items-start justify-between">
        <div>
          <div className="text-sm font-semibold text-text">{player.name}</div>
          <div className="text-xs text-text-faint">
            {player.team} {player.opponent ? `vs ${player.opponent}` : ""}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="text-text-faint hover:text-text">
          ✕
        </button>
      </div>

      <h3 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Projection Comparison</h3>

      <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
        <dt className="text-text-faint">External Baseline</dt>
        <dd className="text-right text-text">{fmt(player.externalProjection)}</dd>
        <dt className="text-text-faint">Big Money Independent</dt>
        <dd className="text-right text-text">{fmt(player.projection)}</dd>
        <dt className="text-text-faint">Big Money Adjusted</dt>
        <dd className="text-right text-text">{fmt(player.adjustedProjection)}</dd>
      </dl>

      {!hasComparison && <p className="mt-3 text-xs text-text-faint">No external projection data available for this player.</p>}

      {player.adjustedProjection !== null && player.adjustmentDelta !== null && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Adjustment</h3>
          <div className={`text-sm font-semibold ${player.adjustmentDelta >= 0 ? "text-green" : "text-red"}`}>
            {player.adjustmentDelta >= 0 ? "+" : ""}
            {fmt(player.adjustmentDelta)} ({player.adjustmentDelta >= 0 ? "+" : ""}
            {fmt(player.adjustmentPercent, 1)}%)
          </div>
          {player.adjustmentReasons.length > 0 && (
            <div className="mt-2">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-text-faint">Reasons</div>
              <div className="flex flex-wrap gap-1.5">
                {player.adjustmentReasons.map((r, i) => (
                  <AIInsightBadge key={i}>{r}</AIInsightBadge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
