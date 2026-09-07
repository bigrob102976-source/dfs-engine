"""NFL M7 -- orchestrates the real, current-slate NFL Vegas game-context
pipeline: DK pool -> real DK games -> real odds fetch -> match -> honest
result. Ties together M5's already-real derive_dk_games_from_pool() /
match_dk_games_to_odds() (nfl/odds_matching.py, unmodified) with M7's new
real odds fetch (nfl/odds_provider.py).

Never fabricates: when no odds provider is configured,
build_nfl_game_context() still returns a real NflOddsMatchResult where
every DK game is UNMATCHED (zero odds events to match against) rather
than raising or inventing context -- exactly like an unmatched game from
a configured-but-incomplete provider payload.
"""

from dataclasses import dataclass
from typing import List

from nfl.models import NflPlayer
from nfl.odds_matching import NflOddsMatchResult, derive_dk_games_from_pool, match_dk_games_to_odds
from nfl.odds_provider import NflOddsFetchResult, fetch_nfl_odds_events


@dataclass
class NflGameContextBuildResult:
    match_result: NflOddsMatchResult
    odds_fetch: NflOddsFetchResult
    dk_game_count: int


def build_nfl_game_context(players: List[NflPlayer], draft_group_id: int, slate_date: str) -> NflGameContextBuildResult:
    dk_games = derive_dk_games_from_pool(players)
    odds_fetch = fetch_nfl_odds_events()
    match_result = match_dk_games_to_odds(
        dk_games=dk_games,
        odds_events=odds_fetch.events,
        draft_group_id=draft_group_id,
        slate_date=slate_date,
        source=odds_fetch.source_provenance,
    )
    return NflGameContextBuildResult(match_result=match_result, odds_fetch=odds_fetch, dk_game_count=len(dk_games))
