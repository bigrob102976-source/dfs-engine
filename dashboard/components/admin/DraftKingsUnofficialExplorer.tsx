"use client";

import { useState } from "react";

import { SecondaryButton } from "@/components/ui/Button";

const SPORT_OPTIONS = ["MLB", "NFL", "NBA", "NHL", "GOLF", "NAS", "MMA", "SOC", "TEN", "CFB"];
const TABS = ["SLATE", "GAMES", "PLAYERS", "SALARIES", "CONTESTS", "RULES", "RAW DATA"] as const;
type Tab = (typeof TABS)[number];

interface ExplorerData {
  status: string;
  detail?: string;
  error?: string;
  sport?: string;
  sports?: Array<{ sport_id: number; code: string; full_name: string; has_public_contests: boolean }>;
  slates?: Array<{ draft_group_id: number; game_type_id: number; game_type_name: string | null; tag: string | null; label: string | null; start_time: string | null; game_count: number | null; contest_ids: number[] }>;
  contests?: Array<{ contest_id: number; name: string; game_type: string | null; start_time_iso: string | null; entry_fee: number | null; prize_pool: number | null; max_entries: number | null; current_entries: number | null; draft_group_id: number | null }>;
  slate_detail?: {
    status: string; error?: string | null;
    games?: Array<{ competition_id: number; name: string | null; start_time: string | null; venue: string | null; home_team: { abbreviation: string } | null; away_team: { abbreviation: string } | null }>;
    draftables?: Array<{ draftable_id: number; display_name: string; position: string | null; salary: number | null; team_abbreviation: string | null; status: string | null; roster_slot_id: number | null }>;
    roster_rules?: { name: string; salary_cap: number | null; roster_slots: Array<{ name: string; scoring_multiplier: number | null }> } | null;
    identity_match_summary?: { total: number; matched: number; unmatched: number; ambiguous: number; match_percent: number };
    quality?: Record<string, unknown>;
  };
}

/** Milestone 31.2 -- the admin DraftKings Development Data Explorer.
 * Never auto-fetches on mount/sport-change -- every live request is an
 * explicit admin click ("Load Sport Data" / selecting a slate), per
 * this milestone's conservative-live-calls principle. Labeled
 * throughout as UNOFFICIAL/DEVELOPMENT data -- never presented as a
 * production data source. */
export function DraftKingsUnofficialExplorer() {
  const [sport, setSport] = useState("MLB");
  const [data, setData] = useState<ExplorerData | null>(null);
  const [selectedDraftGroupId, setSelectedDraftGroupId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("SLATE");

  async function loadSport() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/draftkings-unofficial?sport=${encodeURIComponent(sport)}`);
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Failed to load DraftKings data.");
        setData(null);
        return;
      }
      setData(body);
      setSelectedDraftGroupId(null);
    } catch {
      setError("Failed to load DraftKings data -- is the dashboard server running?");
    } finally {
      setLoading(false);
    }
  }

  async function loadSlate(draftGroupId: number, gameTypeId: number) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/draftkings-unofficial?sport=${encodeURIComponent(sport)}&draftGroupId=${draftGroupId}&gameTypeId=${gameTypeId}`);
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Failed to load slate detail.");
        return;
      }
      setData(body);
      setSelectedDraftGroupId(draftGroupId);
    } catch {
      setError("Failed to load slate detail.");
    } finally {
      setLoading(false);
    }
  }

  const selectedSlate = data?.slates?.find((s) => s.draft_group_id === selectedDraftGroupId) ?? null;
  const slateContests = (data?.contests ?? []).filter((c) => c.draft_group_id === selectedDraftGroupId);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded border border-yellow/30 bg-yellow/10 px-3 py-2 text-xs font-medium text-yellow">
        UNOFFICIAL DRAFTKINGS DEVELOPMENT DATA -- sourced from DraftKings&apos; undocumented public endpoints for development only. Never used as a licensed/production data source. See draftkings_unofficial/README.md.
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-border bg-bg-panel p-3">
        <label className="flex items-center gap-2 text-xs text-text-muted">
          Sport
          <select value={sport} onChange={(e) => setSport(e.target.value)} className="rounded border border-border bg-bg-panel-raised px-2 py-1 text-text">
            {SPORT_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <SecondaryButton type="button" disabled={loading} onClick={loadSport}>
          {loading ? "Loading..." : "Load Sport Data"}
        </SecondaryButton>

        {data?.slates && data.slates.length > 0 && (
          <label className="flex items-center gap-2 text-xs text-text-muted">
            Slate (DraftGroup)
            <select
              value={selectedDraftGroupId ?? ""}
              onChange={(e) => {
                const dg = data.slates!.find((s) => s.draft_group_id === Number(e.target.value));
                if (dg) loadSlate(dg.draft_group_id, dg.game_type_id);
              }}
              className="min-w-[260px] rounded border border-border bg-bg-panel-raised px-2 py-1 text-text"
            >
              <option value="">Select a DraftGroup...</option>
              {data.slates.map((s) => (
                <option key={s.draft_group_id} value={s.draft_group_id}>
                  {s.draft_group_id} -- {s.game_type_name ?? s.game_type_id} {s.tag ? `[${s.tag}]` : ""}{s.label ?? ""} ({s.game_count ?? "?"} games, {s.contest_ids.length} contests)
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error && <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">{error}</div>}

      {data?.status === "not_enabled" && (
        <div className="rounded border border-border-subtle bg-bg-panel-raised px-3 py-2 text-xs text-text-faint">
          {data.detail ?? "DK_UNOFFICIAL_ENABLED is not set."}
        </div>
      )}
      {data?.status === "no_active_slate" && (
        <div className="rounded border border-border-subtle bg-bg-panel-raised px-3 py-2 text-xs text-text-faint">
          NO ACTIVE SLATE for {data.sport} right now.
        </div>
      )}

      {data?.status === "ok" && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
              <div className="text-[10px] uppercase text-text-faint">Sport</div>
              <div className="text-sm font-semibold text-text">{data.sport}</div>
            </div>
            <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
              <div className="text-[10px] uppercase text-text-faint">DraftGroups</div>
              <div className="text-sm font-semibold text-text">{data.slates?.length ?? 0}</div>
            </div>
            <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
              <div className="text-[10px] uppercase text-text-faint">Contests</div>
              <div className="text-sm font-semibold text-text">{data.contests?.length ?? 0}</div>
            </div>
            <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
              <div className="text-[10px] uppercase text-text-faint">Selected DraftGroup</div>
              <div className="text-sm font-semibold text-text">{selectedDraftGroupId ?? "--"}</div>
            </div>
          </div>

          {data.slate_detail && (
            <>
              <div className="flex gap-1 border-b border-border-subtle">
                {TABS.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTab(t)}
                    className={`px-3 py-1.5 text-xs font-medium uppercase tracking-wide ${tab === t ? "border-b-2 border-accent text-accent" : "text-text-faint hover:text-text-muted"}`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {data.slate_detail.status !== "ok" && (
                <div className="rounded border border-red bg-bg-panel-raised px-3 py-2 text-xs text-red">
                  {data.slate_detail.status}: {data.slate_detail.error ?? ""}
                </div>
              )}

              {data.slate_detail.status === "ok" && (
                <div className="rounded border border-border-subtle bg-bg-panel-raised p-3">
                  {tab === "SLATE" && selectedSlate && (
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                      <dt className="text-text-faint">DraftGroup</dt><dd className="text-text">{selectedSlate.draft_group_id}</dd>
                      <dt className="text-text-faint">Game Type</dt><dd className="text-text">{selectedSlate.game_type_name ?? selectedSlate.game_type_id}</dd>
                      <dt className="text-text-faint">Games</dt><dd className="text-text">{data.slate_detail.games?.length ?? 0}</dd>
                      <dt className="text-text-faint">Draftables</dt><dd className="text-text">{data.slate_detail.draftables?.length ?? 0}</dd>
                      <dt className="text-text-faint">Contests</dt><dd className="text-text">{slateContests.length}</dd>
                      <dt className="text-text-faint">Identity Match %</dt><dd className="text-text">{data.slate_detail.identity_match_summary?.match_percent ?? "--"}%</dd>
                    </dl>
                  )}

                  {tab === "GAMES" && (
                    <table className="w-full text-xs">
                      <thead><tr className="text-left text-text-faint"><th>Away</th><th>Home</th><th>Start</th><th>Venue</th></tr></thead>
                      <tbody>
                        {(data.slate_detail.games ?? []).map((g) => (
                          <tr key={g.competition_id} className="border-t border-border-subtle/60">
                            <td className="py-1">{g.away_team?.abbreviation ?? "--"}</td>
                            <td>{g.home_team?.abbreviation ?? "--"}</td>
                            <td>{g.start_time ?? "--"}</td>
                            <td>{g.venue ?? "--"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {tab === "PLAYERS" && (
                    <table className="w-full text-xs">
                      <thead><tr className="text-left text-text-faint"><th>Name</th><th>Team</th><th>Position</th><th>Status</th></tr></thead>
                      <tbody>
                        {(data.slate_detail.draftables ?? []).slice(0, 500).map((d) => (
                          <tr key={d.draftable_id} className="border-t border-border-subtle/60">
                            <td className="py-1">{d.display_name}</td>
                            <td>{d.team_abbreviation ?? "--"}</td>
                            <td>{d.position ?? "--"}</td>
                            <td>{d.status ?? "--"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {tab === "SALARIES" && (
                    <table className="w-full text-xs">
                      <thead><tr className="text-left text-text-faint"><th>Name</th><th>Roster Slot</th><th className="text-right">Salary</th></tr></thead>
                      <tbody>
                        {[...(data.slate_detail.draftables ?? [])].sort((a, b) => (b.salary ?? 0) - (a.salary ?? 0)).slice(0, 500).map((d) => (
                          <tr key={d.draftable_id} className="border-t border-border-subtle/60">
                            <td className="py-1">{d.display_name}</td>
                            <td>{d.roster_slot_id ?? "--"}</td>
                            <td className="text-right">{d.salary != null ? `$${d.salary.toLocaleString()}` : "--"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {tab === "CONTESTS" && (
                    <table className="w-full text-xs">
                      <thead><tr className="text-left text-text-faint"><th>Name</th><th>Entry Fee</th><th>Prize Pool</th><th>Entries</th></tr></thead>
                      <tbody>
                        {slateContests.map((c) => (
                          <tr key={c.contest_id} className="border-t border-border-subtle/60">
                            <td className="py-1">{c.name}</td>
                            <td>{c.entry_fee != null ? `$${c.entry_fee}` : "--"}</td>
                            <td>{c.prize_pool != null ? `$${c.prize_pool.toLocaleString()}` : "--"}</td>
                            <td>{c.current_entries ?? "--"} / {c.max_entries ?? "--"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {tab === "RULES" && data.slate_detail.roster_rules && (
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                      <dt className="text-text-faint">Game Type</dt><dd className="text-text">{data.slate_detail.roster_rules.name}</dd>
                      <dt className="text-text-faint">Salary Cap</dt><dd className="text-text">{data.slate_detail.roster_rules.salary_cap ?? "--"}</dd>
                      <dt className="text-text-faint">Roster Slots</dt>
                      <dd className="text-text">{data.slate_detail.roster_rules.roster_slots.map((s) => `${s.name}${s.scoring_multiplier ? ` (${s.scoring_multiplier}x)` : ""}`).join(", ")}</dd>
                    </dl>
                  )}

                  {tab === "RAW DATA" && (
                    <pre className="max-h-96 overflow-auto text-[10px] text-text-faint">
                      {JSON.stringify({ quality: data.slate_detail.quality, identity_match_summary: data.slate_detail.identity_match_summary }, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
