"use client";

import { useState } from "react";

import { GameCenterDrawer } from "./GameCenterDrawer";
import { SlateRankingCard } from "./SlateRankingCard";
import { SectionHeader } from "@/components/ui/Header";
import type { VegasSlateAnalysis } from "@/lib/gameEnvironment";
import type { AiRankedPlayer, GameRanking } from "@/lib/commandCenter";
import type { PitcherRecord } from "@/lib/types";

/** CENTER COLUMN client shell: owns which game's Game Center is open.
 * `rankings` is pre-sorted (highest combined score first) by
 * lib/commandCenter.ts::buildGameRankings on the server. */
export function SlateRankingsColumn({
  rankings,
  pitcherRecords,
  hitterRows,
  pitcherRows,
  analysis,
}: {
  rankings: GameRanking[];
  pitcherRecords: PitcherRecord[];
  hitterRows: AiRankedPlayer[];
  pitcherRows: AiRankedPlayer[];
  analysis: VegasSlateAnalysis | null;
}) {
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const selected = rankings.find((r) => r.game.game_id === selectedGameId) ?? null;

  return (
    <div>
      <SectionHeader title="Slate Rankings" />
      {rankings.length === 0 ? (
        <p className="rounded-[var(--radius-card)] border border-dashed border-border bg-bg-panel px-4 py-8 text-center text-xs text-text-faint">
          No games ranked yet -- generate today&apos;s Game Environment report.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {rankings.map((ranking, i) => (
            <SlateRankingCard key={ranking.game.game_id} rank={i + 1} ranking={ranking} onOpen={() => setSelectedGameId(ranking.game.game_id)} />
          ))}
        </div>
      )}

      <GameCenterDrawer
        ranking={selected}
        pitcherRecords={pitcherRecords}
        hitterRows={hitterRows}
        pitcherRows={pitcherRows}
        analysis={analysis}
        onClose={() => setSelectedGameId(null)}
      />
    </div>
  );
}
