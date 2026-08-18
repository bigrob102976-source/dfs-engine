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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from config.game_environment_config import (
    LINE_MOVEMENT_SHARP_RUNS,
    TOTAL_HIGH_THRESHOLD,
    TOTAL_LOW_THRESHOLD,
)
from research.game_environment import game_status as game_status_module
from research.game_environment.models import BookLineSnapshot, VegasLine, VegasSlateAnalysis, VegasSnapshot
from research.game_environment.providers import coverage as coverage_module
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
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
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
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
    ) -> VegasSnapshot:
        # Milestone 25: defaults to PREGAME (unchanged prior behavior --
        # every existing test/call site that doesn't pass mlb_game_status
        # still gets the same always-fresh mock line it always has), but
        # respects an explicitly-passed status so dev/mock mode can also
        # be used to exercise pregame-lock/freeze UI without a real key.
        resolved_status = (
            game_status_module.classify_mlb_game_status(mlb_game_status) if mlb_game_status else game_status_module.PREGAME
        )
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

        if resolved_status == game_status_module.PREGAME:
            projection_status = "LIVE_PREGAME"
        elif resolved_status == game_status_module.IN_PLAY:
            projection_status = "IN_PLAY_ONLY"
        else:
            projection_status = "MISSING"

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
            game_status=resolved_status,
            is_frozen_pregame=False,
            vegas_projection_status=projection_status,
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
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
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
            # Milestone 25: only a snapshot that was ITSELF captured while
            # the game was genuinely PREGAME counts as an observation for
            # "First Observed" -- a frozen carryover (repeating an older
            # snapshot's data after the game went live) must never be
            # mistaken for a new data point (see module docstring above
            # this file's SportsGameOddsVegasProvider for why this can't
            # practically happen with the current oldest-first scan order,
            # but this keeps the guarantee explicit rather than incidental).
            if vegas.get("game_status") != game_status_module.PREGAME:
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


def _vegas_line_from_dict(d: Optional[dict]) -> VegasLine:
    d = d or {}
    return VegasLine(
        moneyline=d.get("moneyline"), run_line=d.get("run_line"),
        run_line_odds=d.get("run_line_odds"), total=d.get("total"),
    )


def _book_line_snapshot_from_dict(d: dict) -> BookLineSnapshot:
    return BookLineSnapshot(
        book=d.get("book", ""), home_moneyline=d.get("home_moneyline"), away_moneyline=d.get("away_moneyline"),
        total=d.get("total"), total_over_odds=d.get("total_over_odds"), total_under_odds=d.get("total_under_odds"),
        home_run_line=d.get("home_run_line"), away_run_line=d.get("away_run_line"),
        home_run_line_odds=d.get("home_run_line_odds"), away_run_line_odds=d.get("away_run_line_odds"),
        last_updated=d.get("last_updated"),
    )


def _vegas_snapshot_from_dict(vegas: dict) -> VegasSnapshot:
    """Deserializes a saved VegasSnapshot dict (from an immutable Game
    Environment snapshot on disk) back into a real VegasSnapshot object
    -- used only to reuse an OLDER pregame snapshot verbatim (freezing),
    never to reinterpret/recompute its values."""
    return VegasSnapshot(
        game_id=vegas["game_id"], home_team=vegas["home_team"], away_team=vegas["away_team"],
        provider_name=vegas.get("provider_name", ""), is_mock=bool(vegas.get("is_mock", False)),
        retrieved_at=vegas.get("retrieved_at", ""),
        opening_home=_vegas_line_from_dict(vegas.get("opening_home")),
        opening_away=_vegas_line_from_dict(vegas.get("opening_away")),
        current_home=_vegas_line_from_dict(vegas.get("current_home")),
        current_away=_vegas_line_from_dict(vegas.get("current_away")),
        home_implied_runs=vegas.get("home_implied_runs"), away_implied_runs=vegas.get("away_implied_runs"),
        total_movement=vegas.get("total_movement"), moneyline_movement_home=vegas.get("moneyline_movement_home"),
        event_id=vegas.get("event_id"),
        books=[_book_line_snapshot_from_dict(b) for b in (vegas.get("books") or [])],
        books_used=list(vegas.get("books_used") or []),
        market_count=vegas.get("market_count", 0),
        consensus_method=vegas.get("consensus_method"),
        consensus_home_win_probability=vegas.get("consensus_home_win_probability"),
        consensus_away_win_probability=vegas.get("consensus_away_win_probability"),
        implied_runs_calculation_method=vegas.get("implied_runs_calculation_method"),
        implied_runs_input_total=vegas.get("implied_runs_input_total"),
        implied_runs_input_home_run_line=vegas.get("implied_runs_input_home_run_line"),
        implied_runs_input_home_moneyline=vegas.get("implied_runs_input_home_moneyline"),
        implied_runs_input_away_moneyline=vegas.get("implied_runs_input_away_moneyline"),
        implied_runs_is_valid=bool(vegas.get("implied_runs_is_valid", True)),
        validation_warnings=list(vegas.get("validation_warnings") or []),
        is_first_pull_of_day=bool(vegas.get("is_first_pull_of_day", True)),
        game_status=vegas.get("game_status", game_status_module.UNKNOWN),
        is_frozen_pregame=bool(vegas.get("is_frozen_pregame", False)),
        vegas_projection_status=vegas.get("vegas_projection_status", "MISSING"),
        selected_provider=vegas.get("selected_provider"),
        fallback_used=bool(vegas.get("fallback_used", False)),
        primary_provider_status=vegas.get("primary_provider_status"),
        secondary_provider_status=vegas.get("secondary_provider_status"),
        missing_reason=vegas.get("missing_reason"),
    )


def _resolve_last_valid_pregame(slate_date: str, game_id: str, snapshot_root=None) -> Optional[VegasSnapshot]:
    """Scans this project's own saved Game Environment snapshots for
    `slate_date`, NEWEST first, for the LATEST one where `game_id`'s
    Vegas data was: (1) genuinely captured while PREGAME (not itself a
    frozen carryover -- see is_frozen_pregame check below), (2) real
    (is_mock is False), and (3) a VALID implied-runs calculation. Returns
    a full VegasSnapshot ready for direct reuse (its own original
    retrieved_at preserved), or None if no such snapshot was ever
    captured today -- the caller must then report Vegas as MISSING, never
    inventing or backfilling one. This is the single implementation
    behind get_projection_vegas_snapshot()/get_vegas_line()'s freeze path
    AND "Pregame Close" (the same value, once the game leaves PREGAME)."""
    from research.game_environment import storage  # lazy import: avoids a module-load-time cycle with storage's own imports

    root = snapshot_root if snapshot_root is not None else storage.DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT
    for path in reversed(storage.list_environment_reports(slate_date, output_root=root)):
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
            if vegas.get("is_frozen_pregame"):
                continue  # only an ORIGINAL pregame capture, never a repeat of an earlier freeze
            if vegas.get("game_status") != game_status_module.PREGAME:
                continue
            if not vegas.get("implied_runs_is_valid", True):
                continue
            if vegas.get("home_implied_runs") is None or vegas.get("away_implied_runs") is None:
                continue
            return _vegas_snapshot_from_dict(vegas)

    return None


def get_projection_vegas_snapshot(game_id: str, slate_date: str, snapshot_root=None) -> Optional[VegasSnapshot]:
    """Public helper (Milestone 25): the exact Vegas snapshot Native/AI
    projections are allowed to use for `game_id` on `slate_date`, purely
    from THIS project's own saved history -- no network call. Returns
    the latest valid PREGAME snapshot (which may already be frozen from
    an earlier fetch), or None if none was ever captured. Equivalent to
    what SportsGameOddsVegasProvider.get_vegas_line() itself falls back
    to once a game is no longer PREGAME; exposed standalone for
    evaluation/research code that wants "what would the projection have
    used" without re-running the whole collector pipeline."""
    return _resolve_last_valid_pregame(slate_date, game_id, snapshot_root=snapshot_root)


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

    def _fetch_and_build_current(
        self, game_id: str, home_team_abbr: str, away_team_abbr: str, slate_date: Optional[str], mlb_game_status: Optional[str]
    ) -> VegasSnapshot:
        """Always returns whatever the market says RIGHT NOW, correctly
        classified/labeled -- regardless of whether the game is still
        pregame. Milestone 25's get_vegas_line() below is the only method
        allowed to hand a live in-play/final/unknown result to a
        projection; it never returns this directly except when the
        classification IS PREGAME. get_live_vegas_line() returns this
        verbatim for research/history display."""
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
                f"No {self.provider_name()} MLB event matched {away_team_abbr}@{home_team_abbr} for {resolved_date}."
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

        # Milestone 25: MLB Stats API status is authoritative; SportsGameOdds'
        # own event status is only a fallback (game_status.resolve_game_status).
        resolved_status = game_status_module.resolve_game_status(mlb_game_status, matched.event_status)

        if resolved_status == game_status_module.PREGAME:
            if implied.is_valid:
                projection_status = "LIVE_PREGAME"
            elif implied.calculation_method and implied.calculation_method.startswith("unavailable_"):
                projection_status = "MISSING"
            else:
                projection_status = "INVALID"
        elif resolved_status == game_status_module.IN_PLAY:
            projection_status = "IN_PLAY_ONLY"
        else:  # FINAL or UNKNOWN
            projection_status = "MISSING"

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
            game_status=resolved_status,
            is_frozen_pregame=False,
            vegas_projection_status=projection_status,
            selected_provider=self.provider_name() if projection_status == "LIVE_PREGAME" else None,
            fallback_used=False,
            primary_provider_status=(coverage_module.VALID if projection_status == "LIVE_PREGAME" else None),
            secondary_provider_status=None,
        )

    def get_vegas_line(
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
    ) -> VegasSnapshot:
        """Milestone 25: the ONLY value Native/AI projections may
        consume. Returns the current fetch directly when (and only when)
        it's genuinely PREGAME; otherwise NEVER lets in-play/final/
        unknown market data reach a projection -- it freezes to the last
        valid PREGAME snapshot this project has already captured for
        this game today, or (if none exists) returns an honest
        zero-contribution snapshot with vegas_projection_status
        "IN_PLAY_ONLY"/"MISSING" and implied_runs_is_valid=False, so
        `team_implied_runs` is None and the existing (unchanged) "if
        team_implied_runs is not None" guards in native_projections/
        matchup.py and projection_engine/signals.py already exclude it
        -- no new gating code needed there."""
        resolved_date = slate_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current = self._fetch_and_build_current(game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status)

        if current.game_status == game_status_module.PREGAME:
            return current

        frozen = _resolve_last_valid_pregame(resolved_date, game_id, snapshot_root=self._snapshot_root)
        if frozen is not None:
            frozen.is_frozen_pregame = True
            frozen.vegas_projection_status = "PREGAME_FROZEN"
            return frozen

        return VegasSnapshot(
            game_id=game_id, home_team=home_team_abbr, away_team=away_team_abbr,
            provider_name=self.provider_name(), is_mock=False, retrieved_at=current.retrieved_at,
            opening_home=VegasLine(), opening_away=VegasLine(), current_home=VegasLine(), current_away=VegasLine(),
            home_implied_runs=None, away_implied_runs=None, total_movement=None, moneyline_movement_home=None,
            event_id=current.event_id, implied_runs_is_valid=False,
            validation_warnings=[
                f"No valid pregame Vegas snapshot was ever captured for this game before it went {current.game_status}."
            ],
            is_first_pull_of_day=False,
            game_status=current.game_status,
            is_frozen_pregame=False,
            vegas_projection_status=("IN_PLAY_ONLY" if current.game_status == game_status_module.IN_PLAY else "MISSING"),
        )

    def get_live_vegas_line(
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
    ) -> VegasSnapshot:
        """Milestone 25: ALWAYS returns the current market snapshot,
        regardless of pregame/in-play/final status -- for research/
        history display only (the Vegas Intelligence page's LIVE MARKET
        tab, GameEnvironmentReport.vegas_live). Native/AI projections
        must never call this; use get_vegas_line(). Not part of the
        abstract VegasProvider interface -- MockVegasProvider/
        NotConfiguredVegasProvider don't define it, so callers check
        `hasattr`/`getattr` defensively (see collector.py)."""
        return self._fetch_and_build_current(game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status)


class TheOddsAPIVegasProvider(SportsGameOddsVegasProvider):
    """Milestone 27 -- SECONDARY/fallback Vegas provider. Deliberately a
    thin subclass rather than a parallel implementation: the entire
    fetch/match/consensus/implied-runs/pregame-lock pipeline in
    SportsGameOddsVegasProvider is already provider-agnostic (it only
    ever calls the injected `odds_provider`'s get_odds(), never
    anything SportsGameOdds-specific) -- swapping in a
    providers/theoddsapi.py::TheOddsAPIProvider instance and overriding
    the display name is the whole difference. This guarantees the two
    providers can never silently drift apart in how they build a
    VegasSnapshot from normalized odds."""

    name = "theoddsapi"

    def provider_name(self) -> str:
        return "The Odds API"


@dataclass
class _ProviderAttempt:
    snapshot: Optional[VegasSnapshot]
    status: str  # coverage_module.VALID | NOT_CONFIGURED | one of ALL_MISSING_REASONS


class MultiProviderVegasProvider(VegasProvider):
    """Milestone 27 -- tries PRIMARY (SportsGameOdds) first; only when
    the primary does not produce a valid PREGAME market for a specific
    game does it attempt SECONDARY (The Odds API), if configured. Never
    blends one provider's moneyline with another's total -- each
    provider independently produces a complete consensus (see
    providers/consensus.py), and this class picks the single
    highest-priority VALID one whole. If neither is valid, Vegas
    contribution is ZERO for that game, with the exact reason recorded
    (providers/coverage.py) rather than a bare "missing"."""

    name = "multi_provider"

    def __init__(
        self,
        primary: SportsGameOddsVegasProvider,
        secondary: Optional[TheOddsAPIVegasProvider] = None,
        snapshot_root=None,
    ):
        self._primary = primary
        self._secondary = secondary
        self._snapshot_root = snapshot_root

    def provider_name(self) -> str:
        if self._secondary is not None and self._secondary.is_configured():
            return f"{self._primary.provider_name()} + {self._secondary.provider_name()} (fallback)"
        return self._primary.provider_name()

    def is_configured(self) -> bool:
        return self._primary.is_configured() or (self._secondary is not None and self._secondary.is_configured())

    def _attempt(
        self,
        provider: Optional[SportsGameOddsVegasProvider],
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str],
        mlb_game_status: Optional[str],
    ) -> _ProviderAttempt:
        """Reaches into SportsGameOddsVegasProvider's own
        _fetch_and_build_current() -- an intentional same-module
        "friend" call (see TheOddsAPIVegasProvider's docstring for why
        that method is already fully provider-agnostic), so this class
        never re-implements consensus/implied-runs logic a second time.
        The provider-level exception message is pattern-matched (rather
        than a richer exception type) only to distinguish "no event
        matched" and "rate limited" from a generic provider error --
        documented here as a known, pragmatic limitation rather than a
        silent guess."""
        if provider is None or not provider.is_configured():
            return _ProviderAttempt(None, coverage_module.NOT_CONFIGURED)

        try:
            snapshot = provider._fetch_and_build_current(  # noqa: SLF001 -- same-module friend call, see docstring
                game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status
            )
        except VegasProviderNotConfiguredError:
            return _ProviderAttempt(None, coverage_module.NOT_CONFIGURED)
        except VegasProviderUnavailableError as exc:
            message = str(exc).lower()
            if "event matched" in message:
                return _ProviderAttempt(None, coverage_module.EVENT_NOT_MATCHED)
            if "rate limit" in message or "quota" in message:
                return _ProviderAttempt(None, coverage_module.PLAN_RESTRICTED)
            return _ProviderAttempt(None, coverage_module.PROVIDER_ERROR)

        if snapshot.game_status != game_status_module.PREGAME:
            return _ProviderAttempt(snapshot, coverage_module.PREGAME_NOT_AVAILABLE)

        has_total = snapshot.current_home.total is not None
        has_moneyline = snapshot.current_home.moneyline is not None and snapshot.current_away.moneyline is not None
        status = coverage_module.classify_missing_reason(
            is_configured=True,
            event_matched=True,
            has_total=has_total,
            has_moneyline=has_moneyline,
            is_pregame=True,
            provider_errored=False,
            rate_limited=False,
        )
        if status == coverage_module.UNKNOWN and not snapshot.implied_runs_is_valid:
            # Total + moneyline both present, but implied runs still
            # couldn't be computed -- no run line was returned. Not one
            # of the milestone's 7 named categories, so UNKNOWN is the
            # honest classification (see coverage.py's own docstring).
            return _ProviderAttempt(snapshot, coverage_module.UNKNOWN)
        if status != coverage_module.UNKNOWN:
            return _ProviderAttempt(snapshot, status)
        return _ProviderAttempt(snapshot, coverage_module.VALID)

    def get_vegas_line(
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
    ) -> VegasSnapshot:
        resolved_date = slate_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        primary = self._attempt(self._primary, game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status)
        secondary = _ProviderAttempt(None, coverage_module.NOT_CONFIGURED)

        selected_snapshot: Optional[VegasSnapshot] = None
        selected_provider_name: Optional[str] = None
        fallback_used = False

        if primary.status == coverage_module.VALID:
            selected_snapshot = primary.snapshot
            selected_provider_name = self._primary.provider_name()
        elif self._secondary is not None:
            secondary = self._attempt(self._secondary, game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status)
            if secondary.status == coverage_module.VALID:
                selected_snapshot = secondary.snapshot
                selected_provider_name = self._secondary.provider_name()
                fallback_used = True

        if selected_snapshot is not None:
            selected_snapshot.selected_provider = selected_provider_name
            selected_snapshot.fallback_used = fallback_used
            selected_snapshot.primary_provider_status = primary.status
            selected_snapshot.secondary_provider_status = secondary.status
            selected_snapshot.missing_reason = None
            return selected_snapshot

        # Neither provider produced a valid PREGAME market right now --
        # fall back to the last valid pregame snapshot EITHER provider
        # already captured and saved today (same freeze mechanism as
        # the single-provider path).
        frozen = _resolve_last_valid_pregame(resolved_date, game_id, snapshot_root=self._snapshot_root)
        if frozen is not None:
            frozen.is_frozen_pregame = True
            frozen.vegas_projection_status = "PREGAME_FROZEN"
            frozen.primary_provider_status = primary.status
            frozen.secondary_provider_status = secondary.status
            return frozen

        best_available = primary.snapshot or secondary.snapshot
        resolved_game_status = best_available.game_status if best_available is not None else game_status_module.classify_mlb_game_status(mlb_game_status)
        missing_reason = (
            primary.status
            if primary.status in coverage_module.ALL_MISSING_REASONS
            else (secondary.status if secondary.status in coverage_module.ALL_MISSING_REASONS else coverage_module.UNKNOWN)
        )

        return VegasSnapshot(
            game_id=game_id, home_team=home_team_abbr, away_team=away_team_abbr,
            provider_name=self.provider_name(), is_mock=False, retrieved_at=_now(),
            opening_home=VegasLine(), opening_away=VegasLine(), current_home=VegasLine(), current_away=VegasLine(),
            home_implied_runs=None, away_implied_runs=None, total_movement=None, moneyline_movement_home=None,
            event_id=best_available.event_id if best_available is not None else None,
            implied_runs_is_valid=False,
            validation_warnings=[
                f"No valid pregame Vegas data from any configured provider "
                f"(primary={primary.status}, secondary={secondary.status})."
            ],
            is_first_pull_of_day=False,
            game_status=resolved_game_status,
            is_frozen_pregame=False,
            vegas_projection_status=("IN_PLAY_ONLY" if resolved_game_status == game_status_module.IN_PLAY else "MISSING"),
            selected_provider=None,
            fallback_used=False,
            primary_provider_status=primary.status,
            secondary_provider_status=secondary.status,
            missing_reason=missing_reason,
        )

    def get_live_vegas_line(
        self,
        game_id: str,
        home_team_abbr: str,
        away_team_abbr: str,
        slate_date: Optional[str] = None,
        mlb_game_status: Optional[str] = None,
    ) -> VegasSnapshot:
        """Research/history display only (see SportsGameOddsVegasProvider's
        own get_live_vegas_line docstring) -- ALWAYS returns the current
        market snapshot regardless of pregame/in-play/final status.
        Prefers the primary provider's raw current fetch whenever it
        produced ANY event match; only falls back to the secondary's raw
        fetch when the primary didn't even match the event."""
        primary = self._attempt(self._primary, game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status)
        if primary.snapshot is not None:
            primary.snapshot.selected_provider = self._primary.provider_name()
            primary.snapshot.primary_provider_status = primary.status
            return primary.snapshot

        if self._secondary is not None:
            secondary = self._attempt(self._secondary, game_id, home_team_abbr, away_team_abbr, slate_date, mlb_game_status)
            if secondary.snapshot is not None:
                secondary.snapshot.selected_provider = self._secondary.provider_name()
                secondary.snapshot.fallback_used = True
                secondary.snapshot.secondary_provider_status = secondary.status
                return secondary.snapshot

        return VegasSnapshot(
            game_id=game_id, home_team=home_team_abbr, away_team=away_team_abbr,
            provider_name=self.provider_name(), is_mock=False, retrieved_at=_now(),
            opening_home=VegasLine(), opening_away=VegasLine(), current_home=VegasLine(), current_away=VegasLine(),
            home_implied_runs=None, away_implied_runs=None, total_movement=None, moneyline_movement_home=None,
            implied_runs_is_valid=False,
            validation_warnings=[f"No event matched by any configured provider (primary={primary.status})."],
            is_first_pull_of_day=False,
            game_status=game_status_module.classify_mlb_game_status(mlb_game_status),
            is_frozen_pregame=False,
            vegas_projection_status="MISSING",
            primary_provider_status=primary.status,
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
