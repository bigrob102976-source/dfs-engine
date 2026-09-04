"use client";

import { useMemo, useState } from "react";

import { SecondaryButton } from "@/components/ui";
import { loadExposureState, saveExposureState, type ExposureState } from "@/lib/nfl/exposureStorage";
import type { NflPlayerRow } from "@/lib/nfl/types";

/** NFL M13 -- a focused, optimizer-only exposure editor (Phase 17's own
 * suggested alternative to cluttering the already-dense Players table
 * with two more input columns). Search adds a player; each active
 * override shows as a compact row with Min%/Max% inputs and a remove
 * button. Persisted per-slate via lib/nfl/exposureStorage.ts, exactly
 * like Lock/Exclude. */
export function NflExposureEditor({ players, draftGroupId }: { players: NflPlayerRow[]; draftGroupId: number }) {
  const [state, setState] = useState<ExposureState>(() => loadExposureState(draftGroupId));
  const [search, setSearch] = useState("");

  const byId = useMemo(() => new Map(players.map((p) => [p.draftkings_player_id, p])), [players]);

  const overrideIds = useMemo(() => {
    const ids = new Set([...Object.keys(state.maxExposure), ...Object.keys(state.minExposure)]);
    return Array.from(ids).filter((id) => byId.has(id));
  }, [state, byId]);

  const searchResults = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (q.length < 2) return [];
    return players.filter((p) => !overrideIds.includes(p.draftkings_player_id) && p.name.toLowerCase().includes(q)).slice(0, 12);
  }, [search, players, overrideIds]);

  function persist(next: ExposureState) {
    setState(next);
    saveExposureState(draftGroupId, next);
  }

  function setMax(id: string, pct: number | null) {
    const next = { ...state, maxExposure: { ...state.maxExposure } };
    if (pct === null) delete next.maxExposure[id];
    else next.maxExposure[id] = Math.max(0, Math.min(100, pct)) / 100;
    persist(next);
  }
  function setMin(id: string, pct: number | null) {
    const next = { ...state, minExposure: { ...state.minExposure } };
    if (pct === null) delete next.minExposure[id];
    else next.minExposure[id] = Math.max(0, Math.min(100, pct)) / 100;
    persist(next);
  }
  function remove(id: string) {
    const next = { maxExposure: { ...state.maxExposure }, minExposure: { ...state.minExposure } };
    delete next.maxExposure[id];
    delete next.minExposure[id];
    persist(next);
  }
  function add(id: string) {
    persist({ ...state, maxExposure: { ...state.maxExposure, [id]: 0.5 } });
    setSearch("");
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search a player to add a Min/Max Exposure override…"
          className="w-full rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2 py-1.5 text-xs text-text"
        />
        {searchResults.length > 0 && (
          <div className="absolute z-10 mt-1 w-full rounded-[var(--radius-control)] border border-border bg-bg-panel shadow-[var(--shadow-card)]">
            {searchResults.map((p) => (
              <button
                key={p.draftkings_player_id}
                onClick={() => add(p.draftkings_player_id)}
                className="block w-full px-2 py-1.5 text-left text-xs text-text hover:bg-bg-panel-raised"
              >
                {p.name} <span className="text-text-faint">({p.position} {p.team})</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {overrideIds.length === 0 ? (
        <p className="text-[11px] text-text-faint">No per-player exposure overrides set -- every player uses the Default Max Exposure above.</p>
      ) : (
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border-subtle text-text-faint">
              <th className="py-1 pr-2 font-medium">Player</th>
              <th className="py-1 pr-2 font-medium">Min Exp %</th>
              <th className="py-1 pr-2 font-medium">Max Exp %</th>
              <th className="py-1 pr-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {overrideIds.map((id) => {
              const p = byId.get(id);
              if (!p) return null;
              return (
                <tr key={id} className="border-b border-border-subtle/50">
                  <td className="py-1 pr-2 text-text">{p.name} <span className="text-text-faint">({p.position} {p.team})</span></td>
                  <td className="py-1 pr-2">
                    <input
                      type="number" min={0} max={100}
                      value={state.minExposure[id] !== undefined ? Math.round(state.minExposure[id] * 100) : ""}
                      onChange={(e) => setMin(id, e.target.value === "" ? null : Number(e.target.value))}
                      className="w-16 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-1.5 py-1 text-xs text-text"
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      type="number" min={0} max={100}
                      value={state.maxExposure[id] !== undefined ? Math.round(state.maxExposure[id] * 100) : ""}
                      onChange={(e) => setMax(id, e.target.value === "" ? null : Number(e.target.value))}
                      className="w-16 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-1.5 py-1 text-xs text-text"
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <SecondaryButton onClick={() => remove(id)} className="px-2 py-0.5 text-[10px]">
                      Remove
                    </SecondaryButton>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
