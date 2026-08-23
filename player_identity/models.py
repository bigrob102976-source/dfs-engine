"""Typed schema for one row of the canonical MLB player identity
crosswalk (player_identity/refresh.py). Deliberately separate from
dfs/models.py::CanonicalPlayer -- that type also carries per-SLATE
context (opponent, game_id) that has nothing to do with player identity
itself; CanonicalIdentity is pure player identity, reusable across every
slate a player appears on.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, Optional


@dataclass
class CanonicalIdentity:
    """One player's canonical MLB identity, as of `last_verified_at`.

    `current_team` ALWAYS comes from the most recent live roster fetch
    that observed this player (player_identity/roster_source.py) --
    never from a historical/stale source (see
    player_identity/historical_backfill.py's module docstring for why).
    `bat_side`/`throw_hand` may be backfilled from the historical
    crosswalk (safe: handedness doesn't change, and that backfill is
    always joined by mlb_player_id, never by name or team).
    """

    mlb_player_id: str
    canonical_name: str
    normalized_name: str
    current_team: str
    position: Optional[str] = None
    player_type: Optional[str] = None  # "pitcher" | "hitter"
    bat_side: Optional[str] = None
    throw_hand: Optional[str] = None
    active: bool = True
    last_verified_at: str = ""
    source: str = "mlb_roster"  # "mlb_roster" | "historical_crosswalk_backfill"

    # Reserved for future provider-alias population (dk_player_id,
    # BlueCollar local id, FantasyPros id, ...) -- deliberately never
    # collapsed into mlb_player_id. Not populated by this milestone
    # (identity resolution only); kept here so the schema is
    # forward-compatible without a later migration.
    aliases: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
