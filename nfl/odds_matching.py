"""NFL M5 -- matches real DraftKings games (derived from the M2
canonical pool) to real odds-provider events, producing NflGameContext
records.

NOT exercised against real odds data as of M5: no odds provider
credentials exist anywhere in this project today (checked this local
environment and the real MLB production Railway deployment -- neither
has SPORTSGAMEODDS_API_KEY, THEODDSAPI_KEY, or any equivalent set).
This module is real, tested (synthetic fixtures), structurally complete
matching logic -- it has simply never been run against a real payload,
and this docstring says so rather than implying otherwise.

Matching strategy: normalized (home_team, away_team) pair, via
config/nfl_team_abbreviations.py's explicit (currently empty) exception
table -- never fuzzy name matching. A DK game matches an odds event only
when both teams normalize to the same pair; more than one odds event
matching the same DK game is reported as AMBIGUOUS and neither is
attached (a wrong Vegas line is worse than a missing one).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config.nfl_team_abbreviations import normalize_odds_provider_team_abbr
from nfl.game_context_models import NflGameContext, derive_implied_totals
from nfl.models import NflPlayer
from research.game_environment.providers.models import NormalizedGameOdds


@dataclass
class DkGameInfo:
    """One real DK game, derived from the M2 canonical pool -- never a
    separate fetch, always DraftKings' own already-verified identity."""

    game_id: str  # DraftKings' own competitionId (== NflPlayer.game_id)
    home_team: str
    away_team: str
    start_time: Optional[str]


def derive_dk_games_from_pool(players: List[NflPlayer]) -> List[DkGameInfo]:
    """Extracts the unique real games on a slate from the canonical
    pool. game_description is DraftKings' own "AWAY @ HOME" string
    (confirmed live, NFL M2) -- parsed here, never guessed."""
    games: Dict[str, DkGameInfo] = {}
    for p in players:
        if p.game_id in games or not p.game_description or " @ " not in p.game_description:
            continue
        away, home = p.game_description.split(" @ ", 1)
        games[p.game_id] = DkGameInfo(game_id=p.game_id, home_team=home.strip(), away_team=away.strip(), start_time=p.game_start_time)
    return list(games.values())


@dataclass
class NflOddsMatchResult:
    games: List[NflGameContext]
    matched_dk_game_ids: List[str]
    unmatched_dk_game_ids: List[str]
    ambiguous_dk_game_ids: List[str]


def match_dk_games_to_odds(
    dk_games: List[DkGameInfo], odds_events: List[NormalizedGameOdds],
    draft_group_id: int, slate_date: str, source: str,
) -> NflOddsMatchResult:
    def normalized_pair(home: str, away: str) -> Tuple[str, str]:
        return (normalize_odds_provider_team_abbr(home), normalize_odds_provider_team_abbr(away))

    events_by_pair: Dict[Tuple[str, str], List[NormalizedGameOdds]] = {}
    for event in odds_events:
        key = normalized_pair(event.home_team, event.away_team)
        events_by_pair.setdefault(key, []).append(event)

    games: List[NflGameContext] = []
    matched: List[str] = []
    unmatched: List[str] = []
    ambiguous: List[str] = []

    for dk_game in dk_games:
        key = normalized_pair(dk_game.home_team, dk_game.away_team)
        candidates = events_by_pair.get(key, [])

        if len(candidates) == 0:
            unmatched.append(dk_game.game_id)
            continue
        if len(candidates) > 1:
            # More than one odds event resolves to the same normalized
            # team pair (e.g. a provider quirk, or two events on
            # different dates sharing this key) -- attaching either
            # would risk a wrong line, so neither is attached.
            ambiguous.append(dk_game.game_id)
            continue

        event = candidates[0]
        book = event.books[0] if event.books else None
        spread = book.home_run_line if book else None
        total = book.total if book else None
        home_implied, away_implied, derivation = derive_implied_totals(spread, total)

        games.append(NflGameContext(
            sport="NFL", draft_group_id=draft_group_id, slate_date=slate_date,
            canonical_game_id=dk_game.game_id, draftkings_game_id=dk_game.game_id,
            external_event_id=event.event_id, home_team=dk_game.home_team, away_team=dk_game.away_team,
            game_start_time=dk_game.start_time,
            spread=spread, total=total,
            home_moneyline=book.home_moneyline if book else None,
            away_moneyline=book.away_moneyline if book else None,
            home_implied_total=home_implied, away_implied_total=away_implied, implied_total_derivation=derivation,
            source=source, source_provenance=source,
            fetched_at=event.retrieved_at, data_timestamp=book.last_updated if book else None,
        ))
        matched.append(dk_game.game_id)

    return NflOddsMatchResult(games=games, matched_dk_game_ids=matched, unmatched_dk_game_ids=unmatched, ambiguous_dk_game_ids=ambiguous)
