"""NFL M5 -- the canonical NFL game-context record: real Vegas/schedule
context for one DraftKings game on one slate.

Deliberately NOT a copy of research/game_environment/models.py's
VegasSnapshot/VegasLine -- those are built around MLB's run-total
framing (research/game_environment/providers/models.py::BookLine even
names its spread fields home_run_line/away_run_line) and
research/game_environment/vegas.py hardcodes get_odds("MLB", ...)
throughout its orchestration. This is a fresh, minimal record scoped to
exactly what M5 needs: DK's own real game identity (canonical_game_id
== NflPlayer.game_id, already proven reliable in M2/M3) plus whatever
real odds data a future provider match attaches -- nothing invented.

Null is valid everywhere below: a game with no odds match yet (no
credentialed provider configured -- confirmed true for every external
source in this project today, MLB included) simply has every odds field
None. home_implied_total/away_implied_total are the ONLY derived
fields in this record, and only ever populated when BOTH spread and
total are real (see implied_total_derivation, which is never silently
left unset when a derived value is present -- see
derive_implied_totals() below).
"""

from dataclasses import asdict, dataclass
from typing import Optional

DERIVED_FROM_SPREAD_AND_TOTAL = "DERIVED_FROM_SPREAD_AND_TOTAL"


@dataclass
class NflGameContext:
    sport: str  # "NFL"
    draft_group_id: int
    slate_date: str

    canonical_game_id: str  # == NflPlayer.game_id -- DraftKings' own real competitionId
    draftkings_game_id: str
    external_event_id: Optional[str] = None  # a matched odds provider's own event id, when matched

    home_team: str = ""
    away_team: str = ""
    game_start_time: Optional[str] = None

    spread: Optional[float] = None  # negative = home favored, matching the odds provider's own sign convention
    total: Optional[float] = None
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None

    home_implied_total: Optional[float] = None
    away_implied_total: Optional[float] = None
    # Explicit, never silent: set whenever home/away_implied_total is
    # populated, so a consumer can never mistake a derived number for a
    # real, provider-quoted team total (no real provider in this
    # project quotes team totals directly today).
    implied_total_derivation: Optional[str] = None

    source: Optional[str] = None
    source_provenance: Optional[str] = None

    fetched_at: Optional[str] = None
    data_timestamp: Optional[str] = None  # the odds provider's own "last updated", when present
    is_stale: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def derive_implied_totals(spread: Optional[float], total: Optional[float]) -> tuple:
    """Standard sportsbook math: home_implied = total/2 - spread/2,
    away_implied = total/2 + spread/2, under the sign convention
    "negative spread = home favored" (matching BookLine's own
    documented convention). Returns (None, None, None) unless BOTH
    spread and total are real -- never partially derived, never guessed
    from one alone."""
    if spread is None or total is None:
        return None, None, None
    home_implied = round((total / 2) - (spread / 2), 2)
    away_implied = round((total / 2) + (spread / 2), 2)
    return home_implied, away_implied, DERIVED_FROM_SPREAD_AND_TOTAL


def team_view(game: NflGameContext, team: str) -> dict:
    """The smallest per-team shape a future feature builder needs,
    derived on demand from the one stored NflGameContext -- never
    persisted as a second record (see this milestone's own "don't
    duplicate information unnecessarily" decision)."""
    if team == game.home_team:
        return {
            "team": team, "opponent": game.away_team, "home_away": "home",
            "spread": game.spread, "game_total": game.total,
            "implied_team_total": game.home_implied_total, "moneyline": game.home_moneyline,
            "game_id": game.canonical_game_id, "game_start_time": game.game_start_time,
            "source": game.source, "data_timestamp": game.data_timestamp,
        }
    if team == game.away_team:
        return {
            "team": team, "opponent": game.home_team, "home_away": "away",
            "spread": -game.spread if game.spread is not None else None, "game_total": game.total,
            "implied_team_total": game.away_implied_total, "moneyline": game.away_moneyline,
            "game_id": game.canonical_game_id, "game_start_time": game.game_start_time,
            "source": game.source, "data_timestamp": game.data_timestamp,
        }
    raise ValueError(f"{team!r} is neither the home ({game.home_team!r}) nor away ({game.away_team!r}) team in game {game.canonical_game_id!r}.")
