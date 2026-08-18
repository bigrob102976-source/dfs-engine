"""Typed shapes for the multi-sport ODDS PROVIDER layer (Milestone 24).

These are PROVIDER-side models -- the per-book, per-market data a real
odds API returns, already normalized into a provider-agnostic shape.
Nothing outside research/game_environment/providers/ should ever touch a
raw provider payload; research/game_environment/vegas.py is the ONLY
consumer, and it converts these into the existing VegasSnapshot/VegasLine
shape (research/game_environment/models.py) the rest of the application
already knows how to read.

Sport-agnostic by design (`league` is a plain string field, not an enum
pinned to MLB) so a future NFL/NBA/NHL provider can reuse this same
shape -- but this milestone only builds the MLB normalization path.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class BookLine:
    """One sportsbook's quoted line for one game, at the moment it was
    fetched. Every field is Optional -- a book missing one market (e.g.
    no run line posted yet) never blocks the others from being stored."""

    book: str  # provider-reported bookmaker id/name, e.g. "draftkings", "fanduel"
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None
    total: Optional[float] = None
    total_over_odds: Optional[int] = None
    total_under_odds: Optional[int] = None
    home_run_line: Optional[float] = None  # negative = home favored, e.g. -1.5
    away_run_line: Optional[float] = None
    home_run_line_odds: Optional[int] = None
    away_run_line_odds: Optional[int] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedGameOdds:
    """Every book's line for one game, provider-agnostic. Built by
    providers/normalizer.py from one provider's raw event payload --
    nothing downstream of this ever sees the raw JSON."""

    provider: str
    event_id: str
    league: str
    home_team: str
    away_team: str
    game_time_utc: Optional[str]
    retrieved_at: str
    books: List[BookLine] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)
    # Milestone 25: the provider's own raw per-event status object (e.g.
    # SportsGameOdds' {"started": bool, "live": bool, "ended": bool,
    # "completed": bool, "cancelled": bool, ...}, confirmed live in
    # Milestone 24's validation) -- used ONLY as a fallback pregame/
    # in-play/final classification signal when MLB Stats API's own
    # authoritative status is unavailable (research/game_environment/
    # game_status.py::resolve_game_status()). Never itself the primary
    # signal.
    event_status: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "event_id": self.event_id,
            "league": self.league,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "game_time_utc": self.game_time_utc,
            "retrieved_at": self.retrieved_at,
            "books": [b.to_dict() for b in self.books],
            "parse_warnings": list(self.parse_warnings),
            "event_status": self.event_status,
        }


@dataclass
class ProviderUsageStatus:
    """Account usage/rate-limit info a provider can optionally report.
    Never includes credentials -- see providers/sportsgameodds.py's
    usage_status() for exactly which official endpoint this comes from."""

    provider: str
    requests_used: Optional[int] = None
    requests_limit: Optional[int] = None
    objects_used: Optional[int] = None
    objects_limit: Optional[int] = None
    retrieved_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
