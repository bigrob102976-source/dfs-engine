"use client";

import { AIInsightBadge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import type { AiSignalContribution } from "@/lib/aiProjections";
import type { PoolPlayerRow } from "@/lib/optimizerWorkspace/types";

function fmt(v: number | null, digits = 1): string {
  return v === null ? "--" : v.toFixed(digits);
}

/** Milestone 20's Signal Breakdown visualization: a horizontal bar per
 * signal, width scaled to |delta| relative to the player's largest
 * signal, colored by direction -- the dashboard rendering of the
 * milestone's own "Weather ██████ / Vegas ████" worked example. */
function SignalBreakdownBar({ signal, maxAbsDelta }: { signal: AiSignalContribution; maxAbsDelta: number }) {
  const widthPercent = maxAbsDelta > 0 ? Math.max(4, (Math.abs(signal.delta) / maxAbsDelta) * 100) : 0;
  const positive = signal.delta >= 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="w-24 shrink-0 text-text-faint">{signal.label}</div>
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-bg-panel-raised">
        <div
          className={`h-full rounded-full ${positive ? "bg-green" : "bg-red"}`}
          style={{ width: `${widthPercent}%` }}
        />
      </div>
      <div className={`w-14 shrink-0 text-right font-semibold ${positive ? "text-green" : "text-red"}`}>
        {positive ? "+" : ""}
        {signal.delta.toFixed(2)}
      </div>
    </div>
  );
}

/** PROJECTION COMPARISON detail (Milestone 17): clearly distinguishes
 * provider-derived data (External Baseline) from Big Money's own
 * analysis (Independent, Adjusted) for one player. Renders a plain "no
 * external data" message rather than an error when no baseline/adjusted
 * snapshot covers this player yet. */
function componentRow(label: string, component: { expected_count: number; dk_points: number } | null | undefined) {
  if (!component) return null;
  return (
    <>
      <dt className="text-text-faint">{label}</dt>
      <dd className="text-right text-text">
        {component.expected_count.toFixed(2)} <span className="text-text-faint">({component.dk_points >= 0 ? "+" : ""}{component.dk_points.toFixed(2)} pts)</span>
      </dd>
    </>
  );
}

export function PlayerDetailModal({ player, onClose }: { player: PoolPlayerRow; onClose: () => void }) {
  const hasComparison = player.externalProjection !== null || player.adjustedProjection !== null;
  const hasAi = player.aiProjection !== null;
  const hasNative = player.nativeProjection !== null;
  const maxAbsSignalDelta = hasAi ? Math.max(0, ...player.aiSignals.map((s) => Math.abs(s.delta))) : 0;

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
        <dt className="text-text-faint">BlueCollar</dt>
        <dd className="text-right text-text">{player.externalProjection === null ? "NOT LOADED" : fmt(player.externalProjection)}</dd>
        <dt className="text-text-faint">Legacy</dt>
        <dd className="text-right text-text">{fmt(player.projection)}</dd>
        <dt className="text-text-faint">BlueCollar (Adjusted)</dt>
        <dd className="text-right text-text">{player.adjustedProjection === null ? "NOT LOADED" : fmt(player.adjustedProjection)}</dd>
        <dt className="text-text-faint">FantasyPros</dt>
        <dd className="text-right text-text">
          {player.fantasyProsProjection === null ? "NOT AVAILABLE" : fmt(player.fantasyProsProjection)}
          {player.fantasyProsMatchStatus && player.fantasyProsMatchStatus !== "matched" && (
            <span className="ml-1 text-[10px] text-text-faint">({player.fantasyProsMatchStatus})</span>
          )}
        </dd>
      </dl>

      {!hasComparison && <p className="mt-3 text-xs text-text-faint">BlueCollar: NOT LOADED for this player.</p>}

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

      {/* Milestone 23: Native Projection Model -- Big Money's own
          bottom-up projection built from expected opportunities (PA /
          innings-BF), regressed event rates, and DraftKings scoring --
          independent of BlueCollar/external providers. Shows every
          component so it's clear WHY the projection is what it is. */}
      {hasNative && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-purple">Big Money Native</h3>

          <div className="mt-1 grid grid-cols-4 gap-2 text-center">
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Projection</div>
              <div className="text-xs font-semibold text-purple">{fmt(player.nativeProjection)}</div>
            </div>
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Ceiling</div>
              <div className="text-xs font-semibold text-text">{fmt(player.nativeCeiling)}</div>
            </div>
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Floor</div>
              <div className="text-xs font-semibold text-text">{fmt(player.nativeFloor)}</div>
            </div>
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Confidence</div>
              <div className="text-xs font-semibold text-text">{fmt(player.nativeConfidence, 0)}</div>
            </div>
          </div>

          {player.nativeExpectedPa !== null && (
            <div className="mt-2 text-xs text-text-faint">
              Expected PA <span className="font-semibold text-text">{player.nativeExpectedPa.toFixed(1)}</span>
            </div>
          )}
          {player.nativeExpectedInnings !== null && (
            <div className="mt-2 text-xs text-text-faint">
              Expected IP <span className="font-semibold text-text">{player.nativeExpectedInnings.toFixed(1)}</span>
            </div>
          )}

          {player.nativeHitterComponents && (
            <dl className="mt-3 grid grid-cols-2 gap-y-1.5 text-xs">
              {componentRow("Singles", player.nativeHitterComponents.singles)}
              {componentRow("Doubles", player.nativeHitterComponents.doubles)}
              {componentRow("Triples", player.nativeHitterComponents.triples)}
              {componentRow("Home Runs", player.nativeHitterComponents.home_runs)}
              {componentRow("Walks + HBP", {
                expected_count: player.nativeHitterComponents.walks.expected_count + player.nativeHitterComponents.hit_by_pitch.expected_count,
                dk_points: player.nativeHitterComponents.walks.dk_points + player.nativeHitterComponents.hit_by_pitch.dk_points,
              })}
              {componentRow("Stolen Bases", player.nativeHitterComponents.stolen_bases)}
              {componentRow("Runs", player.nativeHitterComponents.runs)}
              {componentRow("RBI", player.nativeHitterComponents.rbi)}
            </dl>
          )}

          {player.nativePitcherComponents && (
            <dl className="mt-3 grid grid-cols-2 gap-y-1.5 text-xs">
              {componentRow("Innings Pitched", player.nativePitcherComponents.innings_pitched)}
              {componentRow("Strikeouts", player.nativePitcherComponents.strikeouts)}
              {componentRow("Walks", player.nativePitcherComponents.walks)}
              {componentRow("Hits Allowed", player.nativePitcherComponents.hits_allowed)}
              {componentRow("Earned Runs", player.nativePitcherComponents.earned_runs)}
              <dt className="text-text-faint">Win Probability</dt>
              <dd className="text-right text-text">
                {player.nativePitcherComponents.win_probability !== null
                  ? `${(player.nativePitcherComponents.win_probability * 100).toFixed(0)}%${player.nativePitcherComponents.win_probability_is_mock ? " (mock)" : ""}`
                  : "n/a"}
              </dd>
            </dl>
          )}

          {player.nativeReasons.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-text-faint">Reasons</div>
              <div className="flex flex-wrap gap-1.5">
                {player.nativeReasons.map((r, i) => (
                  <AIInsightBadge key={i}>{r}</AIInsightBadge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {!hasNative && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Big Money Native</h3>
          <p className="text-xs text-text-faint">No Native Projection generated yet for this player -- run scripts/run_native_projection_engine.py.</p>
        </div>
      )}

      {/* Milestone 20: AI Projection Engine -- combines every research
          signal already computed elsewhere (weather/Vegas/bullpen/park/
          ownership/matchup/recent form/external gap) into one number,
          with every signal contribution and reason shown here. */}
      {hasAi && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-purple">Big Money AI</h3>

          {/* Legacy/BlueCollar/BlueCollar (Adjusted) already shown above
              in "Projection Comparison" -- this section adds only its
              OWN unique value (Big Money AI's delta from Native) rather
              than re-listing the same three baseline numbers twice. */}
          <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
            <dt className="font-semibold text-purple">Big Money AI (Final)</dt>
            <dd className="text-right font-semibold text-purple">{fmt(player.aiProjection)}</dd>
            <dt className="text-text-faint">Delta from Native</dt>
            <dd className={`text-right font-semibold ${player.nativeProjection !== null && player.aiProjection !== null ? ((player.aiProjection - player.nativeProjection) >= 0 ? "text-green" : "text-red") : "text-text-muted"}`}>
              {player.nativeProjection !== null && player.aiProjection !== null
                ? `${player.aiProjection - player.nativeProjection >= 0 ? "+" : ""}${(player.aiProjection - player.nativeProjection).toFixed(1)}`
                : "--"}
            </dd>
          </dl>

          <div className="mt-3 grid grid-cols-4 gap-2 text-center">
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Ceiling</div>
              <div className="text-xs font-semibold text-text">{fmt(player.aiCeiling)}</div>
            </div>
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Floor</div>
              <div className="text-xs font-semibold text-text">{fmt(player.aiFloor)}</div>
            </div>
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Confidence</div>
              <div className="text-xs font-semibold text-text">{fmt(player.aiConfidence, 0)}</div>
            </div>
            <div className="rounded border border-border-subtle p-1.5">
              <div className="text-[10px] uppercase text-text-faint">Risk</div>
              <div className="text-xs font-semibold text-text">{fmt(player.aiRisk, 0)}</div>
            </div>
          </div>

          <div className="mt-2 flex items-center justify-between text-xs">
            <span className="text-text-faint">
              Grade <span className="font-semibold text-purple">{player.aiGrade ?? "--"}</span>
            </span>
            <span className="text-text-faint">
              Value <span className="font-semibold text-text">{fmt(player.aiValueScore, 2)}</span> pts/$1k
            </span>
            <span className="text-text-faint">
              Total Adj{" "}
              <span className={`font-semibold ${(player.aiDelta ?? 0) >= 0 ? "text-green" : "text-red"}`}>
                {(player.aiDelta ?? 0) >= 0 ? "+" : ""}
                {fmt(player.aiDelta, 2)}
              </span>
            </span>
          </div>

          {player.aiSignals.length > 0 && (
            <div className="mt-3">
              <div className="mb-1.5 text-[11px] uppercase tracking-wide text-text-faint">Signal Breakdown</div>
              <div className="flex flex-col gap-1.5">
                {player.aiSignals.map((s, i) => (
                  <SignalBreakdownBar key={`${s.category}-${i}`} signal={s} maxAbsDelta={maxAbsSignalDelta} />
                ))}
              </div>
            </div>
          )}

          {player.aiReasons.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-text-faint">AI Reasons</div>
              <div className="flex flex-wrap gap-1.5">
                {player.aiReasons.map((r, i) => (
                  <AIInsightBadge key={i}>{r}</AIInsightBadge>
                ))}
              </div>
            </div>
          )}

          {player.aiSummary && <p className="mt-3 text-xs italic text-text-muted">{player.aiSummary}</p>}
        </div>
      )}
      {!hasAi && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Big Money AI</h3>
          <p className="text-xs text-text-faint">No AI Projection generated yet for this player -- run scripts/run_ai_projection_engine.py.</p>
        </div>
      )}

      {/* Milestone 32.2B: Big Money ML -- SHADOW MODE evaluation
          competitor, comparison-only. Data Quality is model-input
          completeness, never a calibrated confidence. */}
      {player.mlProjection !== null ? (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Big Money ML (Shadow)</h3>
          <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
            <dt className="text-text-faint">Projection</dt>
            <dd className="text-right font-semibold text-purple">{fmt(player.mlProjection)}</dd>
            <dt className="text-text-faint">ML Data Quality</dt>
            <dd className="text-right text-text">{player.mlDataQualityScore === null ? "--" : `${Math.round(player.mlDataQualityScore * 100)}%`}</dd>
            <dt className="text-text-faint">ML Model Version</dt>
            <dd className="text-right text-text">{player.playerType === "hitter" ? "Hitter Model v1.0.0" : "Pitcher Model v1.0.0"}</dd>
            <dt className="text-text-faint">Status</dt>
            <dd className="text-right text-text">{player.mlProjectionStatus === "PREGAME_FROZEN" ? "Frozen (pregame)" : "Live pregame"}</dd>
            <dt className="text-text-faint">Projected At</dt>
            <dd className="text-right text-text">{player.mlFeatureTimestamp ? new Date(player.mlFeatureTimestamp).toLocaleString() : "--"}</dd>
          </dl>
        </div>
      ) : (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Big Money ML (Shadow)</h3>
          <p className="text-xs text-text-faint">
            {player.mlProjectionStatus === "MISSING"
              ? "NO VALID PREGAME ML PROJECTION for this player."
              : "Big Money ML: NOT AVAILABLE for this player (starters only)."}
          </p>
        </div>
      )}
    </Modal>
  );
}
