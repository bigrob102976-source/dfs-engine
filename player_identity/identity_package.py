"""Builds a WIDENED identity-resolution package for
dfs/player_resolver.py::build_canonical_index/resolve_all -- the
integration point between the roster-derived canonical crosswalk
(player_identity/refresh.py) and the existing, unmodified matching
tiers in dfs/player_resolver.py.

CRITICAL SEPARATION: the widened package this module returns is used
ONLY for identity resolution (dfs/pool_builder.py passes it to
build_canonical_index/resolve_all). It must NEVER be passed to
dfs/eligibility.py::compute_eligibility, which must keep reading the
ORIGINAL, narrow, confirmed-lineup-only package["pitchers"]/
package["batters"] -- that is what keeps "a player can be identity-
resolved but not optimizer-eligible" true. dfs/pool_builder.py enforces
this by calling compute_eligibility with the original `package`, never
with this module's output.
"""

from typing import Dict, List, Optional, Tuple

from player_identity.models import CanonicalIdentity


def _team_game_context(games: List[dict]) -> Dict[str, Tuple[str, str]]:
    """{team_abbr: (game_id, opponent_abbr)} from today's schedule
    (research_output/<date>/games.json -- schedule-derived, available
    before any lineup posts). On a same-day doubleheader, the first game
    for a team wins (a documented, minor limitation -- the existing
    lineup-confirmed pipeline doesn't fully disambiguate doubleheaders
    either; not solved here to avoid scope creep beyond identity
    resolution)."""
    context: Dict[str, Tuple[str, str]] = {}
    for game in games:
        game_id = game.get("game_id")
        home = game.get("home_team_abbr")
        away = game.get("away_team_abbr")
        if not game_id or not home or not away:
            continue
        context.setdefault(home, (game_id, away))
        context.setdefault(away, (game_id, home))
    return context


def build_identity_package(package: dict, crosswalk: Dict[str, CanonicalIdentity]) -> dict:
    """Returns a NEW dict shaped exactly like `package` (games/teams/
    pitchers/batters), with every crosswalk player whose CURRENT team is
    playing today -- and who isn't already present in the original
    confirmed-lineup pitchers/batters lists -- appended as an extra
    identity candidate. `package` itself is never mutated."""
    games = package.get("games", [])
    team_context = _team_game_context(games)

    existing_pitcher_ids = {str(r["player_id"]) for r in package.get("pitchers", [])}
    existing_batter_ids = {str(r["player_id"]) for r in package.get("batters", [])}

    extra_pitchers: List[dict] = []
    extra_batters: List[dict] = []

    for identity in crosswalk.values():
        ctx = team_context.get(identity.current_team)
        if ctx is None:
            continue  # this player's current team has no game today -- not relevant to this slate
        game_id, opponent_abbr = ctx
        record = {
            "player_id": identity.mlb_player_id,
            "name": identity.canonical_name,
            "team_abbr": identity.current_team,
            "opponent_abbr": opponent_abbr,
            "game_id": game_id,
        }
        if identity.player_type == "pitcher":
            if identity.mlb_player_id in existing_pitcher_ids:
                continue
            extra_pitchers.append(record)
        elif identity.player_type == "hitter":
            if identity.mlb_player_id in existing_batter_ids:
                continue
            extra_batters.append(record)
        # player_type of neither "pitcher" nor "hitter" (shouldn't
        # happen -- roster_source.py always sets one of the two): never
        # guessed, simply not added as an identity candidate.

    return {
        "games": package.get("games", []),
        "teams": package.get("teams", []),
        "pitchers": list(package.get("pitchers", [])) + extra_pitchers,
        "batters": list(package.get("batters", [])) + extra_batters,
    }
