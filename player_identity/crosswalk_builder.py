"""Turns one team's parsed roster entries (player_identity/roster_source.py)
into CanonicalIdentity records -- the persistent, lineup-independent
identity this milestone adds. Pure functions, no network/disk access.
"""

from typing import Dict, List, Optional, Tuple

from dfs.name_normalization import normalize_name

from player_identity.models import CanonicalIdentity


def build_team_identities(
    team_abbr: str,
    roster_entries: List[dict],
    verified_at: str,
    handedness_by_mlb_id: Optional[Dict[str, Tuple[Optional[str], Optional[str]]]] = None,
) -> List[CanonicalIdentity]:
    """One CanonicalIdentity per roster entry, `current_team` set to
    `team_abbr` (the team this roster was fetched FOR -- always current,
    live data, never inferred). `handedness_by_mlb_id` is an OPTIONAL
    backfill (player_identity/historical_backfill.py); a player not in
    it simply keeps bat_side/throw_hand as None, never guessed."""
    handedness_by_mlb_id = handedness_by_mlb_id or {}
    identities: List[CanonicalIdentity] = []
    for entry in roster_entries:
        bat_side, throw_hand = handedness_by_mlb_id.get(entry["mlb_player_id"], (None, None))
        identities.append(CanonicalIdentity(
            mlb_player_id=entry["mlb_player_id"],
            canonical_name=entry["name"],
            normalized_name=normalize_name(entry["name"]),
            current_team=team_abbr,
            position=entry.get("position_abbr"),
            player_type=entry.get("player_type"),
            bat_side=bat_side,
            throw_hand=throw_hand,
            active=bool(entry.get("active", True)),
            last_verified_at=verified_at,
            source="mlb_roster",
        ))
    return identities
