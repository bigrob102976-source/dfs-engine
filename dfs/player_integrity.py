"""Milestone 27.3 -- full DK player identity/type integrity validator.

Runs after dfs/pool_builder.py assembles the unified DFSPlayer pool. Pure
and read-only: it never mutates a player or "fixes" a bad row, it only
classifies each one VALID / WARNING / INVALID with explicit reasons, so
a caller can surface a real problem instead of silently living with it.

Checks performed, per player:

1. team is present and non-empty
2. team is one of the slate's known teams (from the resolved research
   games list)
3. opponent, when present, is one of the slate's known teams
4. team != opponent
5. game_id, when present, resolves to a real game whose home/away teams
   are exactly {team, opponent}
6. player_type agrees with DraftKings' own position-eligibility class
   (P/SP/RP -> pitcher, everything else -> hitter) -- DK position is
   always authoritative, so any disagreement here is INVALID, not a
   judgment call
7. when matched to an MLB identity, the canonical record's own team
   agrees with the DK row's team (a WARNING, not INVALID, since a
   genuine team-abbreviation alias the canonical index doesn't yet
   normalize could legitimately disagree in benign ways -- flagged for
   review rather than silently trusted)

"Row preserved" (every DK CSV row produces exactly one DFSPlayer) is
verified by the caller comparing len(dk_rows) == len(players) -- that
invariant lives one level up in dfs/pool_builder.py, not here, since
this module only ever sees players that already exist.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dfs.models import CanonicalPlayer, DFSPlayer
from dfs.player_resolver import PITCHER_DK_POSITIONS

VALID = "VALID"
WARNING = "WARNING"
INVALID = "INVALID"

_SEVERITY_RANK = {VALID: 0, WARNING: 1, INVALID: 2}


@dataclass
class PlayerIntegrityResult:
    dk_player_id: str
    name: str
    team: str
    status: str
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"dk_player_id": self.dk_player_id, "name": self.name, "team": self.team,
                "status": self.status, "reasons": list(self.reasons)}


def dk_position_class(dk_positions: List[str]) -> Optional[str]:
    """DraftKings position eligibility, classified. None means the row
    supplied no position data at all (cannot judge)."""
    if not dk_positions:
        return None
    return "pitcher" if PITCHER_DK_POSITIONS.intersection(dk_positions) else "hitter"


def _known_teams(games: List[dict]) -> set:
    teams = set()
    for g in games:
        teams.add(g.get("home_team_abbr"))
        teams.add(g.get("away_team_abbr"))
    teams.discard(None)
    return teams


def validate_player(
    player: DFSPlayer,
    games_by_id: Dict[str, dict],
    known_teams: set,
    canonical_by_id: Optional[Dict[str, CanonicalPlayer]] = None,
) -> PlayerIntegrityResult:
    canonical_by_id = canonical_by_id or {}
    reasons: List[str] = []
    status = VALID

    def flag(level: str, message: str) -> None:
        nonlocal status
        reasons.append(message)
        if _SEVERITY_RANK[level] > _SEVERITY_RANK[status]:
            status = level

    if not player.team:
        flag(INVALID, "missing team")
    elif known_teams and player.team not in known_teams:
        flag(WARNING, f"team '{player.team}' is not among this slate's resolved teams {sorted(known_teams)}")

    if player.opponent is not None:
        if player.opponent == player.team:
            flag(INVALID, f"opponent equals team ({player.team})")
        elif known_teams and player.opponent not in known_teams:
            flag(WARNING, f"opponent '{player.opponent}' is not among this slate's resolved teams {sorted(known_teams)}")

    if player.game_id is not None:
        game = games_by_id.get(player.game_id)
        if game is None:
            flag(WARNING, f"game_id '{player.game_id}' does not correspond to any resolved slate game")
        else:
            matchup = {game.get("home_team_abbr"), game.get("away_team_abbr")}
            if player.team not in matchup:
                flag(INVALID, f"game_id '{player.game_id}' ({game.get('away_team_abbr')}@{game.get('home_team_abbr')}) "
                               f"does not include this player's team ({player.team})")
            elif player.opponent is not None and player.opponent not in matchup:
                flag(INVALID, f"game_id '{player.game_id}' ({game.get('away_team_abbr')}@{game.get('home_team_abbr')}) "
                               f"does not include this player's opponent ({player.opponent})")

    dk_type = dk_position_class(player.dk_positions)
    if dk_type is not None and player.player_type != dk_type:
        flag(INVALID, f"player_type '{player.player_type}' disagrees with DK position eligibility "
                       f"{player.dk_positions} (DK positions => '{dk_type}')")

    if player.match_status == "matched" and player.mlb_player_id in canonical_by_id:
        canonical = canonical_by_id[player.mlb_player_id]
        if canonical.team != player.team:
            flag(WARNING, f"matched MLB identity's own canonical team ({canonical.team}) "
                           f"disagrees with this DK row's team ({player.team})")

    return PlayerIntegrityResult(dk_player_id=player.dk_player_id, name=player.name, team=player.team,
                                  status=status, reasons=reasons)


def validate_pool(
    players: List[DFSPlayer], games: List[dict], canonical_by_id: Optional[Dict[str, CanonicalPlayer]] = None,
) -> List[PlayerIntegrityResult]:
    games_by_id = {g["game_id"]: g for g in games}
    known_teams = _known_teams(games)
    return [validate_player(p, games_by_id, known_teams, canonical_by_id) for p in players]


def summarize(results: List[PlayerIntegrityResult]) -> dict:
    return {
        "total": len(results),
        "valid": sum(1 for r in results if r.status == VALID),
        "warning": sum(1 for r in results if r.status == WARNING),
        "invalid": sum(1 for r in results if r.status == INVALID),
        "invalid_rows": [r.to_dict() for r in results if r.status == INVALID],
        "warning_rows": [r.to_dict() for r in results if r.status == WARNING],
    }
