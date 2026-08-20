import { runPythonScript, tail } from "./orchestrator/pythonRunner";
import { parseLastJsonLine } from "./optimizerWorkspace/jsonLine";

// Milestone 31.2 -- read-only, admin-triggered loader for the
// DraftKings Development Data Explorer. Every call here is a REAL live
// request to DraftKings' unofficial endpoints (via
// scripts/dk_unofficial_explorer.py) -- only invoked when an admin
// opens/refreshes the explorer page, never on a schedule or from any
// member-facing code path. Gated server-side by DK_UNOFFICIAL_ENABLED
// (see that script and dfs/providers/draftkings_unofficial_provider.py) --
// this loader itself has no separate gate; "not_enabled" is just
// another status value it passes through honestly.

export interface DkUnofficialSport {
  sport_id: number;
  code: string;
  full_name: string;
  has_public_contests: boolean;
  is_enabled: boolean;
  sort_order: number | null;
}

export interface DkUnofficialSlate {
  draft_group_id: number;
  sport_id: number;
  sport_code: string;
  game_type_id: number;
  game_type_name: string | null;
  start_time: string | null;
  tag: string | null;
  label: string | null;
  game_count: number | null;
  contest_ids: number[];
}

export interface DkUnofficialContest {
  contest_id: number;
  name: string;
  sport_id: number | null;
  draft_group_id: number | null;
  game_type: string | null;
  game_type_id: number | null;
  start_time_iso: string | null;
  entry_fee: number | null;
  prize_pool: number | null;
  max_entries: number | null;
  current_entries: number | null;
  is_guaranteed: boolean | null;
  is_starred: boolean | null;
}

export interface DkUnofficialSlateGame {
  competition_id: number;
  sport_id: number | null;
  name: string | null;
  start_time: string | null;
  home_team: { team_id: number; abbreviation: string; name: string | null } | null;
  away_team: { team_id: number; abbreviation: string; name: string | null } | null;
  venue: string | null;
  state: string | null;
}

export interface DkUnofficialDraftable {
  draftable_id: number;
  draft_group_id: number;
  player_id: number | null;
  player_dk_id: number | null;
  display_name: string;
  position: string | null;
  roster_slot_id: number | null;
  salary: number | null;
  status: string | null;
  team_id: number | null;
  team_abbreviation: string | null;
  competition_id: number | null;
  news_status: string | null;
}

export interface DkUnofficialRosterSlot {
  roster_slot_id: number;
  name: string;
  description: string | null;
  order: number | null;
  scoring_multiplier: number | null;
}

export interface DkUnofficialRosterRules {
  game_type_id: number;
  sport_id: number | null;
  name: string;
  draft_type: string | null;
  salary_cap_enabled: boolean;
  salary_cap: number | null;
  roster_slots: DkUnofficialRosterSlot[];
  unique_players: boolean | null;
  allow_late_swap: boolean | null;
  rules_url: string | null;
}

export interface DkUnofficialSlateDetail {
  status: string;
  error?: string | null;
  games?: DkUnofficialSlateGame[];
  draftables?: DkUnofficialDraftable[];
  roster_rules?: DkUnofficialRosterRules | null;
  identity_match_summary?: { total: number; matched: number; unmatched: number; ambiguous: number; match_percent: number };
  quality?: Record<string, unknown>;
  skipped?: unknown[];
}

export interface DkUnofficialExplorerResult {
  status: "not_enabled" | "no_active_slate" | "ok" | string;
  detail?: string;
  sport?: string;
  sports?: DkUnofficialSport[];
  slates?: DkUnofficialSlate[];
  contests?: DkUnofficialContest[];
  game_types?: unknown[];
  slate_detail?: DkUnofficialSlateDetail;
  error?: string;
}

export async function loadDkUnofficialExplorerData(
  sport: string, draftGroupId?: number, gameTypeId?: number,
): Promise<DkUnofficialExplorerResult | { error: string }> {
  const args = ["--sport", sport];
  if (draftGroupId !== undefined) args.push("--draft-group-id", String(draftGroupId));
  if (gameTypeId !== undefined) args.push("--game-type-id", String(gameTypeId));

  const result = await runPythonScript("scripts/dk_unofficial_explorer.py", args);
  const doc = parseLastJsonLine(result.stdout);
  if (!doc || result.exitCode !== 0) {
    return { error: `DraftKings unofficial explorer failed: ${tail(result.stdout + result.stderr, 800)}` };
  }
  return doc as unknown as DkUnofficialExplorerResult;
}
