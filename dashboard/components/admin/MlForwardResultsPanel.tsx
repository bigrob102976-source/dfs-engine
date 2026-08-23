"use client";

import { useMemo, useState } from "react";

import { CollectResultsButton } from "@/components/admin/CollectResultsButton";
import { DataCard, MetricCard } from "@/components/ui/Card";
import { pivotModelDisagreements } from "@/lib/mlForwardResultsTypes";
import type { MlForwardResultsDocument, MlSourceMetricsRow } from "@/lib/mlForwardResultsTypes";

function fmt(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "--" : value.toFixed(digits);
}

const PLAYER_TABS = ["hitters", "pitchers", "combined"] as const;
type PlayerTab = (typeof PLAYER_TABS)[number];

function SourceMetricsTable({ rows }: { rows: MlSourceMetricsRow[] }) {
  if (rows.length === 0) {
    return <p className="text-[11px] text-text-faint">No shared-sample comparison available yet -- collect results once games are final.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border-subtle text-left text-[10px] uppercase tracking-wide text-text-faint">
            <th className="px-2 py-1">Source</th>
            <th className="px-2 py-1 text-right">N</th>
            <th className="px-2 py-1 text-right">MAE</th>
            <th className="px-2 py-1 text-right">RMSE</th>
            <th className="px-2 py-1 text-right">Pearson</th>
            <th className="px-2 py-1 text-right">Spearman</th>
            <th className="px-2 py-1 text-right">Top-5</th>
            <th className="px-2 py-1 text-right">Top-10</th>
            <th className="px-2 py-1 text-right">Top-20</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source} className={`border-b border-border-subtle/50 ${r.source === "big_money_ml" ? "bg-purple/10" : ""}`}>
              <td className="px-2 py-1 font-medium text-text">{r.source === "big_money_ml" ? "BIG MONEY ML" : r.source.toUpperCase()}</td>
              <td className="px-2 py-1 text-right">{r.shared_sample_n}</td>
              <td className="px-2 py-1 text-right">{fmt(r.mae)}</td>
              <td className="px-2 py-1 text-right">{fmt(r.rmse)}</td>
              <td className="px-2 py-1 text-right">{fmt(r.pearson, 3)}</td>
              <td className="px-2 py-1 text-right">{fmt(r.spearman, 3)}</td>
              <td className="px-2 py-1 text-right">{fmt(r.avg_top5_hit_rate)}</td>
              <td className="px-2 py-1 text-right">{fmt(r.avg_top10_hit_rate)}</td>
              <td className="px-2 py-1 text-right">{fmt(r.avg_top20_hit_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type LineupSortKey = "actual" | "difference" | "projected";

export function MlForwardResultsPanel({ date, slateId, document }: { date: string; slateId: string; document: MlForwardResultsDocument | null }) {
  const [tab, setTab] = useState<PlayerTab>("hitters");
  const [lineupSort, setLineupSort] = useState<LineupSortKey>("actual");

  const disagreements = useMemo(() => {
    if (!document) return [];
    const rows = pivotModelDisagreements(document.player_grading.combined);
    return [...rows].sort((a, b) => Math.abs(b.ml_vs_native ?? b.ml_vs_ai ?? 0) - Math.abs(a.ml_vs_native ?? a.ml_vs_ai ?? 0));
  }, [document]);

  const sortedLineups = useMemo(() => {
    if (!document) return [];
    const lineups = document.lineup_grading.lineups.filter((l) => l.fully_graded);
    const key = lineupSort;
    return [...lineups].sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity));
  }, [document, lineupSort]);

  if (!document) {
    return (
      <DataCard title="Slate Results" action={<CollectResultsButton date={date} slateId={slateId} />}>
        <p className="text-xs text-text-faint">
          No forward-results document collected yet for {slateId} ({date}). Click Collect Results to check MLB status and grade whatever is final.
        </p>
      </DataCard>
    );
  }

  const topHits = [...document.player_grading.combined]
    .filter((r) => r.projection_source === "big_money_ml")
    .sort((a, b) => a.absolute_error - b.absolute_error)
    .slice(0, 10);
  const topMisses = [...document.player_grading.combined]
    .filter((r) => r.projection_source === "big_money_ml")
    .sort((a, b) => b.absolute_error - a.absolute_error)
    .slice(0, 10);

  return (
    <div className="flex flex-col gap-4">
      <DataCard title="Slate Results" action={<CollectResultsButton date={date} slateId={slateId} />}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <MetricCard label="DraftGroup" value={slateId.replace("dkunofficial-", "")} />
          <MetricCard label="Date" value={date} />
          <MetricCard label="Games Final" value={`${document.games_final}/${document.games_total}`} tone={document.all_final ? "positive" : "neutral"} />
          <MetricCard label="Players Graded" value={document.players_graded} />
          <MetricCard label="Lineups Graded" value={document.lineups_graded} />
        </div>
        {!document.all_final && <p className="mt-3 text-[11px] text-yellow">PARTIAL RESULTS -- {document.games_total - document.games_final} game(s) not yet final.</p>}
        <p className="mt-1 text-[11px] text-text-faint">
          ML hitters graded: {document.ml_hitters_graded} &middot; ML pitchers graded: {document.ml_pitchers_graded}
        </p>
      </DataCard>

      <DataCard title="Projection Performance">
        <div className="mb-3 flex gap-1" role="tablist" aria-label="Player type">
          {PLAYER_TABS.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`rounded px-2 py-1 text-xs font-medium capitalize ${tab === t ? "bg-accent-dim text-text" : "bg-bg-panel-raised text-text-faint hover:text-text-muted"}`}
            >
              {t}
            </button>
          ))}
        </div>
        <SourceMetricsTable rows={document.source_comparison[tab].source_metrics ?? []} />
      </DataCard>

      <DataCard title="Big Money ML Lineups" action={<span className="text-[11px] text-text-faint">{document.lineup_grading.lineups_fully_graded}/{document.lineup_grading.lineups_total} fully graded</span>}>
        {document.lineup_grading.lineups_fully_graded === 0 ? (
          <p className="text-xs text-text-faint">No fully-graded ML lineups yet.</p>
        ) : (
          <>
            <div className="mb-3 grid grid-cols-3 gap-3 sm:grid-cols-5">
              <MetricCard label="Highest Actual" value={fmt(document.lineup_grading.highest_actual)} />
              <MetricCard label="Average Actual" value={fmt(document.lineup_grading.average_actual)} />
              <MetricCard label="Lowest Actual" value={fmt(document.lineup_grading.lowest_actual)} />
              <MetricCard label="Average Projected" value={fmt(document.lineup_grading.average_projected)} />
              <MetricCard label="Avg Projection Error" value={fmt(document.lineup_grading.average_projection_error)} />
            </div>
            <div className="mb-2 flex gap-1">
              {(["actual", "projected", "difference"] as LineupSortKey[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setLineupSort(key)}
                  className={`rounded px-2 py-1 text-[11px] font-medium capitalize ${lineupSort === key ? "bg-accent-dim text-text" : "bg-bg-panel-raised text-text-faint"}`}
                >
                  Sort: {key === "actual" ? "Actual DK" : key === "projected" ? "Projected DK" : "Projection Error"}
                </button>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-[10px] uppercase tracking-wide text-text-faint">
                    <th className="px-2 py-1">Lineup</th>
                    <th className="px-2 py-1 text-right">Projected</th>
                    <th className="px-2 py-1 text-right">Actual</th>
                    <th className="px-2 py-1 text-right">Error</th>
                    <th className="px-2 py-1 text-right">Salary</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLineups.map((l) => (
                    <tr key={l.lineup_index} className="border-b border-border-subtle/50">
                      <td className="px-2 py-1">#{l.lineup_index}</td>
                      <td className="px-2 py-1 text-right">{fmt(l.projected)}</td>
                      <td className="px-2 py-1 text-right font-semibold text-text">{fmt(l.actual)}</td>
                      <td className={`px-2 py-1 text-right ${(l.difference ?? 0) >= 0 ? "text-green" : "text-red"}`}>{fmt(l.difference)}</td>
                      <td className="px-2 py-1 text-right">{l.salary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </DataCard>

      <DataCard title="Model Disagreements">
        {disagreements.length === 0 ? (
          <p className="text-xs text-text-faint">No shared ML/Native/AI comparisons yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border-subtle text-left text-[10px] uppercase tracking-wide text-text-faint">
                  <th className="px-2 py-1">Player</th>
                  <th className="px-2 py-1 text-right">ML</th>
                  <th className="px-2 py-1 text-right">Native</th>
                  <th className="px-2 py-1 text-right">AI</th>
                  <th className="px-2 py-1 text-right">Actual</th>
                  <th className="px-2 py-1 text-right">ML Error</th>
                  <th className="px-2 py-1 text-right">Native Error</th>
                  <th className="px-2 py-1 text-right">AI Error</th>
                </tr>
              </thead>
              <tbody>
                {disagreements.slice(0, 25).map((r) => (
                  <tr key={r.player_id} className="border-b border-border-subtle/50">
                    <td className="px-2 py-1">{r.name}</td>
                    <td className="px-2 py-1 text-right text-purple">{fmt(r.ml, 1)}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.native, 1)}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.ai, 1)}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.actual_dk, 1)}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.ml_error, 1)}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.native_error, 1)}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.ai_error, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataCard>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <DataCard title="Top ML Player Hits (lowest absolute error)">
          <PlayerHitMissList rows={topHits} />
        </DataCard>
        <DataCard title="Top ML Player Misses (highest absolute error)">
          <PlayerHitMissList rows={topMisses} />
        </DataCard>
      </div>

      <DataCard title="Known ML Monitors">
        <p className="mb-3 text-[11px] text-text-faint">
          Tracking the historical hitter model&apos;s known ceiling-magnitude/zero-game behavior and severe pitcher misses -- informational
          only, never used to recalibrate the frozen model.
        </p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Hitter Ceiling Recall</h4>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border-subtle text-left text-[10px] uppercase tracking-wide text-text-faint">
                  <th className="px-1 py-1">Actual</th>
                  <th className="px-1 py-1 text-right">N</th>
                  <th className="px-1 py-1 text-right">Avg ML</th>
                  <th className="px-1 py-1 text-right">Avg Actual</th>
                  <th className="px-1 py-1 text-right">Bias</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(document.ceiling_monitor.thresholds ?? {}).map(([threshold, row]) => (
                  <tr key={threshold} className="border-b border-border-subtle/50">
                    <td className="px-1 py-1">{Number(threshold).toFixed(0)}+</td>
                    <td className="px-1 py-1 text-right">{row.n}</td>
                    <td className="px-1 py-1 text-right">{fmt(row.avg_predicted)}</td>
                    <td className="px-1 py-1 text-right">{fmt(row.avg_actual)}</td>
                    <td className="px-1 py-1 text-right">{fmt(row.bias)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Zero-Game Monitor</h4>
            <dl className="grid grid-cols-2 gap-y-1 text-xs">
              <dt className="text-text-faint">N</dt>
              <dd className="text-right">{document.zero_game_monitor.n}</dd>
              <dt className="text-text-faint">Avg ML Projection</dt>
              <dd className="text-right">{fmt(document.zero_game_monitor.avg_predicted)}</dd>
              <dt className="text-text-faint">Bias</dt>
              <dd className="text-right">{fmt(document.zero_game_monitor.bias)}</dd>
              <dt className="text-text-faint">MAE</dt>
              <dd className="text-right">{fmt(document.zero_game_monitor.mae)}</dd>
            </dl>
          </div>
          <div>
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Disaster Pitcher Monitor (actual &le; {document.disaster_pitcher_monitor.threshold})</h4>
            <dl className="grid grid-cols-2 gap-y-1 text-xs">
              <dt className="text-text-faint">N</dt>
              <dd className="text-right">{document.disaster_pitcher_monitor.n}</dd>
              <dt className="text-text-faint">Bias</dt>
              <dd className="text-right">{fmt(document.disaster_pitcher_monitor.bias)}</dd>
              <dt className="text-text-faint">MAE</dt>
              <dd className="text-right">{fmt(document.disaster_pitcher_monitor.mae)}</dd>
            </dl>
          </div>
        </div>
      </DataCard>
    </div>
  );
}

function PlayerHitMissList({ rows }: { rows: MlForwardResultsDocument["player_grading"]["combined"] }) {
  if (rows.length === 0) return <p className="text-xs text-text-faint">Nothing graded yet.</p>;
  return (
    <ol className="flex flex-col gap-1 text-xs">
      {rows.map((r, i) => (
        <li key={r.player_id} className="flex items-center justify-between border-b border-border-subtle/50 pb-1">
          <span>
            {i + 1}. {r.name} <span className="text-text-faint">({r.team})</span>
          </span>
          <span className="tabular-nums">
            ML {fmt(r.pregame_projection, 1)} &rarr; Actual {fmt(r.actual_dk, 1)} ({r.error >= 0 ? "+" : ""}
            {fmt(r.error, 1)})
          </span>
        </li>
      ))}
    </ol>
  );
}
