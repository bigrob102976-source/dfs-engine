"""Milestone 32.2B -- resolves the authoritative M30.1-eligible starting
pitchers for a slate date, straight from the already-computed DK player
pool (dfs/eligibility.py's own output, persisted by
scripts/build_dk_player_pool.py). Never recomputes eligibility, never
imports dfs/ (same discipline projection_engine.persistence.
load_latest_dfs_pool already documents for itself)."""

from dataclasses import dataclass
from typing import List, Optional

from projection_engine.persistence import load_latest_dfs_pool

STARTING_PITCHER = "STARTING_PITCHER"


@dataclass
class EligibleStartingPitcher:
    dk_player_id: Optional[str]
    mlb_player_id: str
    name: str
    team: str
    opponent: str
    game_id: Optional[str]
    salary: Optional[int]
    throwing_hand: Optional[str]


@dataclass
class EligibilitySummary:
    raw_dk_pitcher_rows: int
    starting_pitcher_count: int
    ml_eligible_pitcher_count: int


def get_eligible_starting_pitchers(slate_date: str, dfs_input_root=None) -> List[EligibleStartingPitcher]:
    """optimizer_eligible == True AND player_type == 'pitcher' AND
    eligibility_status == 'STARTING_PITCHER' -- the exact M30.1
    equivalent named in the milestone spec. Relievers, bench pitchers,
    and unmatched DK pitcher rows are excluded by construction (they
    never satisfy this condition in the persisted pool)."""
    kwargs = {} if dfs_input_root is None else {"output_root": dfs_input_root}
    pool_doc = load_latest_dfs_pool(slate_date, **kwargs)
    if not pool_doc:
        return []

    eligible = []
    for row in pool_doc.get("players", []):
        if row.get("player_type") != "pitcher":
            continue
        if not row.get("optimizer_eligible"):
            continue
        if row.get("eligibility_status") != STARTING_PITCHER:
            continue
        if not row.get("mlb_player_id"):
            continue  # unmatched -- never project an unresolved identity
        eligible.append(EligibleStartingPitcher(
            dk_player_id=row.get("dk_player_id"), mlb_player_id=str(row["mlb_player_id"]),
            name=row.get("name", ""), team=row.get("team", ""), opponent=row.get("opponent", ""),
            game_id=row.get("game_id"), salary=row.get("salary"), throwing_hand=row.get("throwing_hand"),
        ))
    return eligible


def build_eligibility_summary(slate_date: str, dfs_input_root=None) -> EligibilitySummary:
    kwargs = {} if dfs_input_root is None else {"output_root": dfs_input_root}
    pool_doc = load_latest_dfs_pool(slate_date, **kwargs)
    if not pool_doc:
        return EligibilitySummary(raw_dk_pitcher_rows=0, starting_pitcher_count=0, ml_eligible_pitcher_count=0)

    pitcher_rows = [r for r in pool_doc.get("players", []) if r.get("player_type") == "pitcher"]
    starting = [r for r in pitcher_rows if r.get("eligibility_status") == STARTING_PITCHER]
    ml_eligible = get_eligible_starting_pitchers(slate_date, dfs_input_root=dfs_input_root)
    return EligibilitySummary(
        raw_dk_pitcher_rows=len(pitcher_rows), starting_pitcher_count=len(starting),
        ml_eligible_pitcher_count=len(ml_eligible),
    )
