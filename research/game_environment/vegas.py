"""Vegas odds collection + deterministic slate-wide analysis for the
Game Environment Engine.

Milestone 24: real market data via research/game_environment/providers/
(SportsGameOdds) replaces mock Vegas as the default whenever
SPORTSGAMEODDS_API_KEY is configured. MockVegasProvider still exists,
clearly labeled, for explicit development/demo use (GAME_ENVIRONMENT_PROVIDER
=mock) -- see get_configured_vegas_provider() in collector.py for the
exact resolution order, and this module's SportsGameOddsVegasProvider
for how real per-book data becomes one VegasSnapshot.
"""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from config.game_environment_config import (
    LINE_MOVEMENT_SHARP_RUNS,
    TOTAL_HIGH_THRESHOLD,
    TOTAL_LOW_THRESHOLD,
)
from research.game_environment.models import BookLineSnapshot, VegasLine, VegasSlateAnalysis, VegasSnapshot
from research.game_environment.providers.base import (
    OddsProvider,
    OddsProviderAuthenticationError,
    OddsProviderNotConfiguredError,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.consensus import ConsensusMarket, build_consensus
from research.game_environment.providers.implied_runs import ImpliedRunsResult, compute_team_implied_runs
from research.game_environment.providers.models import BookLine, NormalizedGameOdds


class VegasProviderNotConfiguredError(RuntimeError):
    """No real Vegas odds provider is configured -- a normal, expected
    state today, not a failure."""


class VegasProviderUnavailableError(RuntimeError):
    """The provider is configured but unreachable/erroring."""


class VegasProvider(ABC):
    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_vegas_line(
        self, game_id: str, home_team_abbr: str, away_team_abbr: str, slate_date: Optional[str] = None
    ) -> VegasSnapshot:
        raise NotImplementedError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seeded_fraction(seed: str) -> float:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _moneyline_to_win_probability(moneyline: int) -> float:
    if moneyline < 0:
        return (-moneyline) / ((-moneyline) + 100)
    return 100 / (moneyline + 100)


class MockVegasProvider(VegasProvider):
    """Development/mock Vegas odds provider -- see module docstring.
    Deterministic per game_id, clearly labeled, never presented as a
    real market price, and (Milestone 24) never allowed to influence a
    Native/AI projection labeled real/live -- see
    native_projections/matchup.py and projection_engine/signals.py."""

    name = "mock_vegas_provider"
    is_mock = True

    def provider_name(self) -> str:
        return "MOCK VEGAS"

    def is_configured(self) -> bool:
        return True

    def get_vegas_line(
        self, game_id: str, home_team_abbr: str, away_team_abbr: str, slate_date: Optional[str] = None
    ) -> VegasSnapshot:
        opening_total = round(7.0 + _seeded_fraction(f"{game_id}-total") * 5.0, 1)  # 7.0-12.0
        total_drift = round((_seeded_fraction(f"{game_id}-drift") - 0.5) * 1.6, 1)  # -0.8..+0.8
        current_total = round(opening_total + total_drift, 1)

        # Home moneyline: favorite or underdog, deterministic per game.
        home_is_favorite = _seeded_fraction(f"{game_id}-favorite") >= 0.5
        magnitude = int(110 + _seeded_fraction(f"{game_id}-magnitude") * 140)  # 110-250
        opening_home_ml = -magnitude if home_is_favorite else magnitude
        opening_away_ml = magnitude if home_is_favorite else -magnitude
        ml_drift = int((_seeded_fraction(f"{game_id}-ml-drift") - 0.5) * 40)  # -20..+20
        current_home_ml = opening_home_ml + ml_drift
        current_away_ml = -current_home_ml if abs(current_home_ml) > 100 else opening_away_ml

        home_win_prob = _moneyline_to_win_probability(current_home_ml)
        away_win_prob = 1.0 - home_win_prob
        # A favorite is also expected to score a modestly larger share of the total.
        home_implied = round(current_total * (0.5 + (home_win_prob - 0.5) * 0.3), 2)
        away_implied = round(current_total - home_implied, 2)

        run_line_home = -1.5 if home_is_favorite else 1.5
        run_line_away = -run_line_home

        retrieved_at = _now()
        return VegasSnapshot(
            game_id=game_id, home_team=home_team_abbr, away_team=away_team_abbr,
            provider_name=self.provider_name(), is_mock=True, retrieved_at=retrieved_at,
            opening_home=VegasLine(moneyline=opening_home_ml, run_line=run_line_home, total=opening_total),
            opening_away=VegasLine(moneyline=opening_away_ml, run_line=run_line_away, total=opening_total),
            current_home=VegasLine(moneyline=current_home_ml, run_line=run_line_home, total=current_total),
            current_away=VegasLine(moneyline=current_away_ml, run_line=run_line_away, total=current_total),
            home_implied_runs=home_implied, away_implied_runs=away_implied,
            total_movement=round(current_total - opening_total, 1),
            moneyline_movement_home=current_home_ml - opening_home_ml,
            consensus_method="mock_deterministic_seed",
            implied_runs_calculation_method="mock_dampened_moneyline_skew",
            implied_runs_is_valid=True,
            is_first_pull_of_day=True,
        )


class NotConfiguredVegasProvider(VegasProvider):
    """Returned when neither a real API key nor explicit mock mode is
    configured (Milestone 24's default, safe state). is_configured()
    is False, so collector.py's build_game_report() never calls
    get_vegas_line() on it at all -- vegas simply stays None for every
    game, exactly like weather/bullpen already do when unconfigured."""

    name = "not_configured"
    is_mock = False

    def provider_name(self) -> str:
        return "NOT CONNECTED"

    def is_configured(self) -> bool:
        return False

    def get_vegas_line(
        self, game_id: str, home_team_abbr: str, away_team_abbr: str, slate_date: Optional[str] = None
    ) -> VegasSnapshot:
        raise VegasProviderNotConfiguredError("SPORTSGAMEODDS_API_KEY is not set and mock mode was not explicitly requested.")


def _book_line_snapshot(b: BookLine) -> BookLineSnapshot:
    return BookLineSnapshot(
        book=b.book, home_moneyline=b.home_moneyline, away_moneyline=b.away_moneyline,
        total=b.total, total_over_odds=b.total_over_odds, total_under_odds=b.total_under_odds,
        home_run_line=b.home_run_line, away_run_line=b.away_run_line,
        home_run_line_odds=b.home_run_line_odds, away_run_line_odds=b.away_run_line_odds,
        last_updated=b.last_updated,
    )


def _find_matching_event(
    events: List[NormalizedGameOdds], home_team_abbr: str, away_team_abbr: str
) -> Optional[NormalizedGameOdds]:
    for event in events:
        if event.home_team == home_team_abbr and event.away_team == away_team_abbr:
            return event
    return None


def _resolve_first_observed(slate_date: str, game_id: str, snapshot_root=None) -> Optional[tuple]:
    """Returns (opening_home, opening_away) by scanning THIS project's
    own already-saved Game Environment snapshots for `slate_date`
    (oldest first) for the earliest one that already has real Vegas
    data for `game_id`. Returns None if no prior real snapshot exists
    yet today -- the caller then treats THIS pull as the first-observed
    baseline itself, never a fabricated "opening" value, and never
    labeled a real sportsbook open (see providers/normalizer.py's
    module docstring). `snapshot_root` is threaded through explicitly
    (rather than relying on storage.py's module-level default) so tests
    can point this at an isolated tmp_path without touching real
    project snapshots."""
    from research.game_environment import storage  # lazy import: avoids a module-load-time cycle with storage's own imports

    root = snapshot_root if snapshot_root is not None else storage.DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT
    for path in storage.list_environment_reports(slate_date, output_root=root):
        try:
            doc = storage.load_environment_report(path)
        except (OSError, ValueError):
            continue
        for g in doc.get("games", []):
            if g.get("game_id") != game_id:
                continue
            vegas = g.get("vegas")
            if not vegas or vegas.get("is_mock"):
                continue
            prior_current_home = vegas.get("current_home") or {}
            if prior_current_home.get("total") is None:
                continue
            opening_home = VegasLine(
                moneyline=prior_current_home.get("moneyline"),
                run_line=prior_current_home.get("run_line"),
                run_line_odds=prior_current_home.get("run_line_odds"),
                total=prior_current_home.get("total"),
            )
            prior_current_away = vegas.get("current_away") or {}
            opening_away = VegasLine(
                moneyline=prior_current_away.get("moneyline"),
                run_line=prior_current_away.get("run_line"),
                run_line_odds=prior_current_away.get("run_line_odds"),
                total=prior_current_away.get("total"),
            )
            return opening_home, opening_away

    return None


class SportsGameOddsVegasProvider(VegasProvider):
    """Real, credentialed Vegas provider -- wraps an OddsProvider
    (providers/sportsgameodds.py) and converts its per-book,
    per-event output into ONE VegasSnapshot per game via
    providers/consensus.py + providers/implied_runs.py. is_mock is
    inherited as False."""

    name = "sportsgameodds"

    def __init__(self, odds_provider: OddsProvider, snapshot_root=None):
        self._odds_provider = odds_provider
        self._snapshot_root = snapshot_root
        self._events_cache: Optional[List[NormalizedGameOdds]] = None
        self._events_cache_date: Optional[str] = None

    def provider_name(self) -> str:
        return "SportsGameOdds"

    def is_configured(self) -> bool:
        return self._odds_provider.is_configured()

    def _get_events(self, slate_date: str) -> List[NormalizedGameOdds]:
        # Process-local memoization on top of the provider's own
        # on-disk raw-response cache -- within one engine run, every
        # game's get_vegas_line() call reuses the SAME fetched event
        # list rather than each one re-invoking the (already-cached,
        # but still non-free) provider call.
        if self._events_cache is not None and self._events_cache_date == slate_date:
            return self._events_cache
        events = self._odds_provider.get_odds("MLB", slate_date)
        self._events_cache = events
        self._events_cache_date = slate_date
        return events

    def get_vegas_line(
        self, game_id: str, home_team_abbr: str, away_team_abbr: str, slate_date: Optional[str] = None
    ) -> VegasSnapshot:
        resolved_date = slate_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            events = self._get_events(resolved_date)
        except OddsProviderNotConfiguredError as exc:
            raise VegasProviderNotConfiguredError(str(exc)) from exc
        except (OddsProviderAuthenticationError, OddsProviderRateLimitedError, OddsProviderUnavailableError) as exc:
            raise VegasProviderUnavailableError(str(exc)) from exc

        matched = _find_matching_event(events, home_team_abbr, away_team_abbr)
        retrieved_at = _now()

        if matched is None:
            raise VegasProviderUnavailableError(
                f"No SportsGameOdds MLB event matched {away_team_abbr}@{home_team_abbr} for {resolved_date}."
            )

        consensus: ConsensusMarket = build_consensus(matched.books)
        implied: ImpliedRunsResult = compute_team_implied_runs(consensus)

        current_home = VegasLine(
            moneyline=consensus.home_moneyline, run_line=consensus.home_run_line, total=consensus.total
        )
        current_away = VegasLine(
            moneyline=consensus.away_moneyline,
            run_line=(-consensus.home_run_line if consensus.home_run_line is not None else None),
            total=consensus.total,
        )

        first_observed = _resolve_first_observed(resolved_date, game_id, snapshot_root=self._snapshot_root)
        is_first_pull = first_observed is None
        opening_home, opening_away = first_observed if first_observed is not None else (current_home, current_away)

        total_movement = (
            round(current_home.total - opening_home.total, 2)
            if current_home.total is not None and opening_home.total is not None
            else None
        )
        moneyline_movement_home = (
            current_home.moneyline - opening_home.moneyline
            if current_home.moneyline is not None and opening_home.moneyline is not None
            else None
        )

        market_count = consensus.total_books_used + consensus.moneyline_books_used + consensus.run_line_books_used

        return VegasSnapshot(
            game_id=game_id, home_team=home_team_abbr, away_team=away_team_abbr,
            provider_name=self.provider_name(), is_mock=False, retrieved_at=retrieved_at,
            opening_home=opening_home, opening_away=opening_away,
            current_home=current_home, current_away=current_away,
            home_implied_runs=implied.home_implied_runs, away_implied_runs=implied.away_implied_runs,
            total_movement=total_movement, moneyline_movement_home=moneyline_movement_home,
            event_id=matched.event_id,
            books=[_book_line_snapshot(b) for b in matched.books],
            books_used=consensus.books_used,
            market_count=market_count,
            consensus_method=consensus.method,
            consensus_home_win_probability=consensus.home_win_probability,
            consensus_away_win_probability=consensus.away_win_probability,
            implied_runs_calculation_method=implied.calculation_method,
            implied_runs_input_total=implied.input_total,
            implied_runs_input_home_run_line=implied.input_home_run_line,
            implied_runs_input_home_moneyline=implied.input_home_moneyline,
            implied_runs_input_away_moneyline=implied.input_away_moneyline,
            implied_runs_is_valid=implied.is_valid,
            validation_warnings=list(matched.parse_warnings) + list(implied.validation_warnings),
            is_first_pull_of_day=is_first_pull,
        )


def analyze_vegas_slate(snapshots: List[VegasSnapshot]) -> VegasSlateAnalysis:
    """Deterministic slate-wide Vegas conclusions -- computed once
    across every game with a snapshot, never per-game."""
    if not snapshots:
        return VegasSlateAnalysis()

    def total_of(s: VegasSnapshot) -> float:
        return s.current_home.total if s.current_home.total is not None else -1.0

    def abs_movement(s: VegasSnapshot) -> float:
        return abs(s.total_movement) if s.total_movement is not None else 0.0

    def home_favorite_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_home.moneyline
        return -ml if ml is not None and ml < 0 else -10_000

    def home_underdog_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_home.moneyline
        return ml if ml is not None and ml > 0 else -10_000

    def away_favorite_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_away.moneyline
        return -ml if ml is not None and ml < 0 else -10_000

    def away_underdog_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_away.moneyline
        return ml if ml is not None and ml > 0 else -10_000

    highest = max(snapshots, key=total_of)
    lowest = min(snapshots, key=total_of)
    largest_move = max(snapshots, key=abs_movement)

    favorite_candidates = [(max(home_favorite_magnitude(s), away_favorite_magnitude(s)), s) for s in snapshots]
    biggest_favorite = max(favorite_candidates, key=lambda pair: pair[0])[1]

    underdog_candidates = [(max(home_underdog_magnitude(s), away_underdog_magnitude(s)), s) for s in snapshots]
    biggest_underdog = max(underdog_candidates, key=lambda pair: pair[0])[1]

    sharp = [s.game_id for s in snapshots if abs_movement(s) >= LINE_MOVEMENT_SHARP_RUNS]

    return VegasSlateAnalysis(
        highest_total_game_id=highest.game_id,
        lowest_total_game_id=lowest.game_id,
        largest_movement_game_id=largest_move.game_id if abs_movement(largest_move) > 0 else None,
        biggest_favorite_game_id=biggest_favorite.game_id,
        biggest_underdog_game_id=biggest_underdog.game_id,
        sharp_movement_game_ids=sharp,
    )


def total_tier(total: Optional[float]) -> str:
    """"high" | "low" | "medium" -- used by scoring.py and the dashboard
    filter for "Highest Totals"."""
    if total is None:
        return "medium"
    if total >= TOTAL_HIGH_THRESHOLD:
        return "high"
    if total <= TOTAL_LOW_THRESHOLD:
        return "low"
    return "medium"
