"""NFL M6C Phase 1/5 -- bridges nflreadpy.load_snap_counts()'s own
identifier space (Pro-Football-Reference's `pfr_player_id`, e.g.
"BankKe01") to GSIS ID.

Real Phase 1 finding: load_snap_counts() carries NO gsis_id column at
all (confirmed live against 2025 -- its 16 real columns are game_id,
pfr_game_id, season, game_type, week, player, pfr_player_id, position,
team, opponent, offense_snaps, offense_pct, defense_snaps, defense_pct,
st_snaps, st_pct). nflreadpy.load_ff_playerids() -- the DynastyProcess-
maintained fantasy-ID crosswalk already identified as reusable during
the M6 audit -- carries BOTH gsis_id and pfr_id for 7,806 real players
(confirmed live), making it a genuine, deterministic ID-to-ID bridge --
never name matching, per Phase 5's explicit rule.

Real, honest limitation (confirmed live against 2025 Week 1): only
81.3% of real snap_counts rows (1,205 of 1,482) resolve to a GSIS ID
through this bridge -- the remainder (mostly deep bench/practice-squad
players DynastyProcess's fantasy-oriented table doesn't track) are
reported as unresolved, never guessed via name matching."""

from typing import Dict, List, Optional

import polars as pl


def build_pfr_to_gsis_bridge(ff_playerids_df: pl.DataFrame) -> Dict[str, str]:
    """`ff_playerids_df` -- the real DataFrame from nflreadpy.load_ff_playerids().
    Returns {pfr_id: gsis_id} for every row where BOTH are present. A
    pfr_id appearing more than once with conflicting gsis_ids keeps
    only the first seen (should not happen in practice -- DynastyProcess's
    table is one row per real person; this is a defensive tie-break, not
    an expected path)."""
    bridge: Dict[str, str] = {}
    filtered = ff_playerids_df.filter(pl.col("pfr_id").is_not_null() & pl.col("gsis_id").is_not_null())
    for row in filtered.iter_rows(named=True):
        bridge.setdefault(row["pfr_id"], row["gsis_id"])
    return bridge


def resolve_gsis_for_snap_row(pfr_player_id: Optional[str], bridge: Dict[str, str]) -> Optional[str]:
    if not pfr_player_id:
        return None
    return bridge.get(pfr_player_id)


def summarize_bridge_coverage(pfr_player_ids: List[str], bridge: Dict[str, str]) -> dict:
    resolved = sum(1 for pid in pfr_player_ids if pid in bridge)
    total = len(pfr_player_ids)
    return {
        "total": total, "resolved": resolved, "unresolved": total - resolved,
        "resolution_rate_percent": round(100.0 * resolved / total, 1) if total else 0.0,
    }
