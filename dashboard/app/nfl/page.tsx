"use client";

import { useMemo, useState } from "react";

import { DataCard, MetricCard } from "@/components/ui";
import { NflPageShell } from "@/components/nfl/NflPageShell";
import { NflStalenessBanner } from "@/components/nfl/NflStalenessBanner";
import {
  buildStacks,
  injuryWatch,
  opponentImpliedTotalFor,
  pickHeadline,
  positionHasNoSpread,
  scoreSlate,
  slateReadiness,
  type ScoredPlayer,
  type StackCandidate,
} from "@/lib/nfl/dashboardMetrics";
import { fmt, fmtSalary } from "@/lib/nfl/format";
import type { NflSlateData } from "@/lib/nfl/types";
import { useNflData } from "@/lib/nfl/useNflData";
import { useNflDraftGroupId } from "@/lib/nfl/useNflDraftGroupId";

const POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;
type Position = (typeof POSITIONS)[number];

/** A named status, never a fabricated 0. */
function Unavailable({ reason }: { reason: string }) {
  return <span className="text-[11px] uppercase tracking-wide text-text-faint">{reason}</span>;
}

function num(value: number | null | undefined, digits = 1) {
  return value === null || value === undefined ? <Unavailable reason="—" /> : <>{fmt(value, digits)}</>;
}

function LeaderCard({
  title,
  subtitle,
  player,
  metric,
  emptyReason,
  lowConfidence,
}: {
  title: string;
  subtitle?: string;
  player: ScoredPlayer | null;
  metric: (p: ScoredPlayer) => string;
  emptyReason: string;
  /** See pickHeadline()'s docstring -- this pick was the only candidate
   * at all, and it has no real game history behind its projection. */
  lowConfidence?: boolean;
}) {
  return (
    <DataCard title={title}>
      {player === null ? (
        <Unavailable reason={emptyReason} />
      ) : (
        <div>
          <div className="flex items-center gap-1.5">
            <div className="text-sm font-semibold text-text">{player.row.name}</div>
            {lowConfidence ? (
              <span
                title="No recent game history — this is the projection model's zero-history fallback value, not a player-specific estimate."
                className="rounded bg-yellow/15 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-yellow"
              >
                Low confidence
              </span>
            ) : null}
          </div>
          <div className="mt-0.5 text-[11px] text-text-faint">
            {player.row.position} · {player.row.team}
            {player.row.opponent ? ` vs ${player.row.opponent}` : ""} · {fmtSalary(player.row.salary)}
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-accent">{metric(player)}</div>
          {subtitle ? <div className="mt-1 text-[11px] leading-snug text-text-faint">{subtitle}</div> : null}
        </div>
      )}
    </DataCard>
  );
}

function StackTable({ rows }: { rows: StackCandidate[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border-subtle text-text-faint">
            {["QB", "Stack", "Bring-back", "Proj", "Ceil", "Own%", "Tm Imp", "Gm Tot"].map((h) => (
              <th key={h} className="py-2 pr-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.qb.row.draftkings_player_id} className="border-b border-border-subtle/50">
              <td className="py-2 pr-3 text-text">{s.qb.row.name}</td>
              <td className="py-2 pr-3 text-text-muted">{s.partners.map((p) => p.row.name).join(", ")}</td>
              <td className="py-2 pr-3 text-text-muted">{s.bringBack ? s.bringBack.row.name : "—"}</td>
              <td className="py-2 pr-3 tabular-nums text-text">{fmt(s.combinedProjection)}</td>
              <td className="py-2 pr-3 tabular-nums text-text-muted">{num(s.combinedCeiling)}</td>
              <td className="py-2 pr-3 tabular-nums text-text-muted">{num(s.combinedOwnership)}</td>
              <td className="py-2 pr-3 tabular-nums text-text-muted">{num(s.teamImpliedTotal)}</td>
              <td className="py-2 pr-3 tabular-nums text-text-muted">{num(s.gameTotal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DashboardContent() {
  const draftGroupId = useNflDraftGroupId();
  const { data, loading, error, refresh } = useNflData(draftGroupId);
  const [tab, setTab] = useState<Position>("QB");

  const scored = useMemo(() => (data ? scoreSlate(data) : []), [data]);
  const qbStacks = useMemo(() => (scored.length ? buildStacks(scored, 1, false) : []), [scored]);
  const gameStacks = useMemo(() => (scored.length ? buildStacks(scored, 2, true) : []), [scored]);

  if (loading && !data) return <p className="text-sm text-text-faint">Loading real NFL slate data…</p>;
  if (error) return <p className="text-sm text-red">{error}</p>;
  if (!data) return null;

  const slate: NflSlateData = data;
  const pricedGames = slate.games.filter((g) => g.total !== null);
  const highestTotal = pricedGames.length ? pricedGames.reduce((a, b) => ((b.total ?? 0) > (a.total ?? 0) ? b : a)) : null;
  const lowestTotal = pricedGames.length ? pricedGames.reduce((a, b) => ((b.total ?? 0) < (a.total ?? 0) ? b : a)) : null;

  const impliedRows = slate.games
    .flatMap((g) => [
      { team: g.lock?.home_team ?? null, total: g.home_implied_total, game: g.game_description },
      { team: g.lock?.away_team ?? null, total: g.away_implied_total, game: g.game_description },
    ])
    .filter((r): r is { team: string; total: number; game: string | null } => r.team !== null && r.total !== null);
  const highestImplied = impliedRows.length ? impliedRows.reduce((a, b) => (b.total > a.total ? b : a)) : null;

  // Both helpers prefer a player with a real track record over the
  // pipeline's zero-history fallback case (see pickHeadline's own
  // docstring) -- only falling back to a zero-history pick when no
  // track-record candidate exists at all, and telling the caller when
  // that happened so the card can say so rather than crown it silently.
  const best = (pos: string, key: (p: ScoredPlayer) => number | null) =>
    pickHeadline(scored.filter((p) => p.row.position === pos), key);
  const topBy = (key: (p: ScoredPlayer) => number | null) => pickHeadline(scored, key);

  const lowConfidenceNote = (p: ScoredPlayer | null) =>
    p && !p.hasTrackRecord
      ? "No recent game history for this pipeline to project from — this is the model's zero-history fallback value, not a player-specific estimate. See Slate Readiness for detail."
      : undefined;

  const dstBaseline = positionHasNoSpread(scored, "DST");
  const bestDst = (() => {
    const pool = scored
      .filter((p) => p.row.position === "DST")
      .map((p) => ({ p, opp: opponentImpliedTotalFor(p.row, slate) }))
      .filter((r): r is { p: ScoredPlayer; opp: number } => r.opp !== null);
    if (!pool.length) return null;
    return pool.reduce((a, b) => (b.opp < a.opp ? b : a)).p;
  })();

  const readiness = slateReadiness(slate);
  const injuries = injuryWatch(slate);
  const tabRows = scored
    .filter((p) => p.row.position === tab)
    .sort((a, b) => (a.bigMoneyRank ?? 9999) - (b.bigMoneyRank ?? 9999));

  const topCash = topBy((p) => p.cashScore);
  const topGpp = topBy((p) => p.gppScore);
  const topValue = topBy((p) => p.value);
  const topLeverage = topBy((p) => p.leverage);
  const topOwned = topBy((p) => p.ownership);

  return (
    <div className="space-y-5">
      <NflStalenessBanner data={slate} />

      {/* Launch Blocker Sprint 1 (2026-09-13): confirmed against real
          production data that a player with zero recent game history
          gets the pipeline's shared imputed-fallback projection rather
          than a real per-player estimate (see pickHeadline()'s
          docstring in dashboardMetrics.ts for the concrete evidence).
          Individual picks are already guarded against crowning that
          case silently (see "Low confidence" tags below), but the
          projection/ranking system as a whole is labeled BETA here
          until the underlying model is retrained with a real
          playing-time-expectation signal. */}
      <div className="rounded-[var(--radius-control)] border border-yellow/30 bg-yellow/5 px-3 py-2 text-[11px] leading-snug text-text-muted">
        <span className="mr-1.5 rounded bg-yellow/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-yellow">
          Beta
        </span>
        NFL projections and rankings are in beta. Players with no recent game history can receive an unreliable
        placeholder projection — these are marked &quot;Low confidence&quot; wherever they appear. Vegas, ownership,
        and Slate Readiness data are not affected by this limitation.
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Slate" value={slate.slate_name?.trim() || `DG ${slate.draft_group_id}`} />
        <MetricCard label="Games" value={slate.game_count} />
        <MetricCard label="Players" value={slate.player_count} />
        <MetricCard label="Salary Cap" value={fmtSalary(slate.salary_cap)} />
        <MetricCard
          label="Pool Status"
          value={slate.data_status === "fresh" ? "Fresh" : "Stale"}
          tone={slate.data_status === "fresh" ? "positive" : "negative"}
        />
        <MetricCard
          label="Vegas"
          value={slate.vegas_configured ? `${pricedGames.length}/${slate.games.length}` : "Awaiting"}
          tone={slate.vegas_configured && pricedGames.length === slate.games.length ? "positive" : "neutral"}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <DataCard title="Highest Game Total">
          {highestTotal ? (
            <div>
              <div className="text-sm font-semibold text-text">{highestTotal.game_description}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-green">{fmt(highestTotal.total)}</div>
            </div>
          ) : (
            <Unavailable reason="AWAITING VEGAS" />
          )}
        </DataCard>
        <DataCard title="Lowest Game Total">
          {lowestTotal ? (
            <div>
              <div className="text-sm font-semibold text-text">{lowestTotal.game_description}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-text">{fmt(lowestTotal.total)}</div>
            </div>
          ) : (
            <Unavailable reason="AWAITING VEGAS" />
          )}
        </DataCard>
        <DataCard title="Highest Implied Team Total">
          {highestImplied ? (
            <div>
              <div className="text-sm font-semibold text-text">{highestImplied.team}</div>
              <div className="mt-0.5 text-[11px] text-text-faint">{highestImplied.game}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-green">{fmt(highestImplied.total)}</div>
            </div>
          ) : (
            <Unavailable reason="AWAITING VEGAS" />
          )}
        </DataCard>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {(["QB", "RB", "WR", "TE"] as const).map((pos) => {
          const { player: p, lowConfidenceFallback } = best(pos, (x) => x.bigMoneyScore);
          return (
            <LeaderCard
              key={pos}
              title={`Best ${pos}`}
              player={p}
              lowConfidence={lowConfidenceFallback}
              metric={(x) => `${fmt(x.bigMoneyScore)} BM`}
              subtitle={p ? (lowConfidenceFallback ? lowConfidenceNote(p) : `${fmt(p.projection)} proj · ${fmt(p.value, 2)} pts/$1K`) : undefined}
              emptyReason="AWAITING PROJECTION"
            />
          );
        })}
        <LeaderCard
          title="Best DST"
          player={bestDst}
          metric={(p) => `${fmt(opponentImpliedTotalFor(p.row, slate))} opp implied`}
          subtitle={
            dstBaseline
              ? "Ranked by opponent implied total. The Big Money Native DST artifact is a positional baseline and returns the same projection for every defense."
              : undefined
          }
          emptyReason={slate.vegas_configured ? "AWAITING PROJECTION" : "AWAITING VEGAS"}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <LeaderCard
          title="Top Cash Play"
          player={topCash.player}
          lowConfidence={topCash.lowConfidenceFallback}
          metric={(p) => `${fmt(p.cashScore)} cash`}
          subtitle={
            topCash.player
              ? topCash.lowConfidenceFallback
                ? lowConfidenceNote(topCash.player)
                : `floor ${fmt(topCash.player.floor)} · ${fmt(topCash.player.value, 2)} pts/$1K`
              : undefined
          }
          emptyReason="AWAITING PROJECTION"
        />
        <LeaderCard
          title="Top GPP Play"
          player={topGpp.player}
          lowConfidence={topGpp.lowConfidenceFallback}
          metric={(p) => `${fmt(p.gppScore)} GPP`}
          subtitle={
            topGpp.player
              ? topGpp.lowConfidenceFallback
                ? lowConfidenceNote(topGpp.player)
                : `ceiling ${fmt(topGpp.player.ceiling)}`
              : undefined
          }
          emptyReason="AWAITING PROJECTION"
        />
        <LeaderCard
          title="Top Value"
          player={topValue.player}
          lowConfidence={topValue.lowConfidenceFallback}
          metric={(p) => `${fmt(p.value, 2)} pts/$1K`}
          subtitle={
            topValue.player
              ? topValue.lowConfidenceFallback
                ? lowConfidenceNote(topValue.player)
                : `${fmt(topValue.player.projection)} proj`
              : undefined
          }
          emptyReason="AWAITING PROJECTION"
        />
        <LeaderCard
          title="Top Leverage"
          player={topLeverage.player}
          lowConfidence={topLeverage.lowConfidenceFallback}
          metric={(p) => `${fmt(p.leverage, 2)} lev`}
          subtitle={
            topLeverage.player
              ? topLeverage.lowConfidenceFallback
                ? lowConfidenceNote(topLeverage.player)
                : `${fmt(topLeverage.player.ownership)}% owned · ceiling ${fmt(topLeverage.player.ceiling)}`
              : undefined
          }
          emptyReason="AWAITING OWNERSHIP"
        />
        <LeaderCard
          title="Highest Owned"
          player={topOwned.player}
          lowConfidence={topOwned.lowConfidenceFallback}
          metric={(p) => `${fmt(p.ownership)}%`}
          subtitle={
            topOwned.player
              ? topOwned.lowConfidenceFallback
                ? lowConfidenceNote(topOwned.player)
                : `${fmt(topOwned.player.projection)} proj`
              : undefined
          }
          emptyReason="AWAITING OWNERSHIP"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <DataCard title="Best QB Stack (QB + pass catcher)">
          {qbStacks.length === 0 ? <Unavailable reason="AWAITING PROJECTION" /> : <StackTable rows={qbStacks.slice(0, 3)} />}
        </DataCard>
        <DataCard title="Best Game Stack (QB + 2 + bring-back)">
          {gameStacks.length === 0 ? <Unavailable reason="AWAITING PROJECTION" /> : <StackTable rows={gameStacks.slice(0, 3)} />}
        </DataCard>
      </div>

      <DataCard
        title="Top Plays by Position"
        action={
          <div className="flex gap-1">
            {POSITIONS.map((p) => (
              <button
                key={p}
                onClick={() => setTab(p)}
                className={`rounded px-2 py-1 text-[11px] font-medium ${
                  tab === p ? "bg-accent/15 text-accent" : "text-text-faint hover:text-text"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        }
      >
        {tab === "DST" && dstBaseline ? (
          <p className="mb-2 text-[11px] leading-snug text-text-faint">
            The Big Money Native DST artifact is a positional baseline: every defense receives the same projection, floor
            and ceiling, so the Big Money rank below carries no per-team opinion. Opponent implied total is the real
            differentiator.
          </p>
        ) : null}
        {tabRows.length === 0 ? (
          <Unavailable reason="AWAITING PROJECTION" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border-subtle text-text-faint">
                  {["#", "Player", "Team", "Opp", "Salary", "Proj", "Floor", "Ceil", "Val", "Own%", "Lev", "Tm Imp", "Gm Tot", "BM"].map(
                    (h) => (
                      <th key={h} className="py-2 pr-3 font-medium">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {tabRows.slice(0, 30).map((p) => (
                  <tr key={p.row.draftkings_player_id} className="border-b border-border-subtle/50">
                    <td className="py-2 pr-3 tabular-nums text-text-faint">{p.bigMoneyRank ?? "—"}</td>
                    <td className="py-2 pr-3 text-text">
                      {p.row.name}
                      {p.row.status_info.normalized_status !== "ACTIVE" ? (
                        <span className="ml-1 text-[10px] uppercase text-red">{p.row.status_info.normalized_status}</span>
                      ) : null}
                      {!p.hasTrackRecord ? (
                        <span
                          title="No recent game history — this projection is the model's zero-history fallback value, not a player-specific estimate."
                          className="ml-1 rounded bg-yellow/15 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-yellow"
                        >
                          Low conf
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3 text-text-muted">{p.row.team}</td>
                    <td className="py-2 pr-3 text-text-muted">{p.row.opponent ?? "—"}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{fmtSalary(p.row.salary)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text">{num(p.projection)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.floor)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.ceiling)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.value, 2)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.ownership)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.leverage, 2)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.teamImpliedTotal)}</td>
                    <td className="py-2 pr-3 tabular-nums text-text-muted">{num(p.gameTotal)}</td>
                    <td className="py-2 pr-3 tabular-nums font-semibold text-accent">{num(p.bigMoneyScore)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataCard>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <DataCard title={`Injury Watch (${injuries.length})`}>
          {injuries.length === 0 ? (
            <p className="text-xs text-text-faint">No non-active statuses reported by DraftKings for this slate.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border-subtle text-text-faint">
                    {["Player", "Pos", "Team", "Salary", "Status"].map((h) => (
                      <th key={h} className="py-2 pr-3 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {injuries.slice(0, 12).map((p) => (
                    <tr key={p.draftkings_player_id} className="border-b border-border-subtle/50">
                      <td className="py-2 pr-3 text-text">{p.name}</td>
                      <td className="py-2 pr-3 text-text-muted">{p.position}</td>
                      <td className="py-2 pr-3 text-text-muted">{p.team}</td>
                      <td className="py-2 pr-3 tabular-nums text-text-muted">{fmtSalary(p.salary)}</td>
                      <td className="py-2 pr-3 font-medium text-red">{p.status_info.normalized_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataCard>

        <DataCard
          title="Slate Readiness"
          action={
            <button onClick={refresh} className="text-xs text-accent hover:underline">
              Refresh
            </button>
          }
        >
          <ul className="space-y-2">
            {readiness.map((r) => (
              <li key={r.label} className="flex items-start justify-between gap-3 text-xs">
                <span className="text-text-muted">{r.label}</span>
                <span className={`text-right ${r.ok ? "text-green" : "text-red"}`}>{r.detail}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] leading-snug text-text-faint">
            Projections: Big Money Native{" "}
            {slate.players.find((p) => p.projection)?.projection?.model_version ?? "—"} · Ownership:{" "}
            {slate.ownership_model_version ?? "—"} · Vegas: {slate.vegas_source_provenance}
          </p>
        </DataCard>
      </div>
    </div>
  );
}

export default function NflDashboardPage() {
  return (
    <NflPageShell title="NFL Dashboard" description="Real DraftKings slate, Big Money Native projections, real Vegas.">
      <DashboardContent />
    </NflPageShell>
  );
}
