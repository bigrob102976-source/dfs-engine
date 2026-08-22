"""Milestone 32.3B -- resolves the authoritative M30.1-eligible starting
hitters for a slate date, straight from the already-computed DK player
pool (dfs/eligibility.py's own output). Mirrors eligible_pitchers.py
exactly, filtered to player_type == "hitter" /
eligibility_status == "STARTING_HITTER" instead of pitchers."""

from dataclasses import dataclass
from typing import List, Optional

from projection_engine.persistence import load_latest_dfs_pool

STARTING_HITTER = "STARTING_HITTER"


@dataclass
class EligibleStartingHitter:
    dk_player_id: Optional[str]
    mlb_player_id: str
    name: str
    team: str
    opponent: str
    game_id: Optional[str]
    salary: Optional[int]
    batting_hand: Optional[str]
    batting_order: Optional[int]


@dataclass
class HitterEligibilitySummary:
    raw_dk_hitter_rows: int
    confirmed_starting_hitter_count: int
    unconfirmed_hitter_count: int
    ml_eligible_hitter_count: int


def get_eligible_starting_hitters(slate_date: str, dfs_input_root=None) -> List[EligibleStartingHitter]:
    """optimizer_eligible == True AND player_type == 'hitter' AND
    eligibility_status == 'STARTING_HITTER'. Bench, unconfirmed, and
    unmatched DK hitter rows are excluded by construction (they never
    satisfy this condition in the persisted pool)."""
    kwargs = {} if dfs_input_root is None else {"output_root": dfs_input_root}
    pool_doc = load_latest_dfs_pool(slate_date, **kwargs)
    if not pool_doc:
        return []

    eligible = []
    for row in pool_doc.get("players", []):
        if row.get("player_type") != "hitter":
            continue
        if not row.get("optimizer_eligible"):
            continue
        if row.get("eligibility_status") != STARTING_HITTER:
            continue
        if not row.get("mlb_player_id"):
            continue
        eligible.append(EligibleStartingHitter(
            dk_player_id=row.get("dk_player_id"), mlb_player_id=str(row["mlb_player_id"]),
            name=row.get("name", ""), team=row.get("team", ""), opponent=row.get("opponent", ""),
            game_id=row.get("game_id"), salary=row.get("salary"), batting_hand=row.get("batting_hand"),
            batting_order=row.get("batting_order"),
        ))
    return eligible


def build_hitter_eligibility_summary(slate_date: str, dfs_input_root=None) -> HitterEligibilitySummary:
    kwargs = {} if dfs_input_root is None else {"output_root": dfs_input_root}
    pool_doc = load_latest_dfs_pool(slate_date, **kwargs)
    if not pool_doc:
        return HitterEligibilitySummary(raw_dk_hitter_rows=0, confirmed_starting_hitter_count=0, unconfirmed_hitter_count=0, ml_eligible_hitter_count=0)

    hitter_rows = [r for r in pool_doc.get("players", []) if r.get("player_type") == "hitter"]
    confirmed = [r for r in hitter_rows if r.get("eligibility_status") == STARTING_HITTER]
    unconfirmed = [r for r in hitter_rows if r.get("eligibility_status") == "LINEUP_UNCONFIRMED"]
    ml_eligible = get_eligible_starting_hitters(slate_date, dfs_input_root=dfs_input_root)
    return HitterEligibilitySummary(
        raw_dk_hitter_rows=len(hitter_rows), confirmed_starting_hitter_count=len(confirmed),
        unconfirmed_hitter_count=len(unconfirmed), ml_eligible_hitter_count=len(ml_eligible),
    )
