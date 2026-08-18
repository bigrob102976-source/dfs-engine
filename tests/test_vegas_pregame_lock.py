"""Milestone 25 -- Pregame Vegas Lock: end-to-end tests for
SportsGameOddsVegasProvider's freeze behavior, get_live_vegas_line(),
and get_projection_vegas_snapshot(). No network calls -- a fake
OddsProvider stands in, same pattern as
test_game_environment_vegas_real_provider.py."""

from research.game_environment import storage as ge_storage
from research.game_environment.providers.base import OddsProvider
from research.game_environment.providers.models import BookLine, NormalizedGameOdds
from research.game_environment.vegas import SportsGameOddsVegasProvider, get_projection_vegas_snapshot


class FakeOddsProvider(OddsProvider):
    name = "fake"
    is_mock = False

    def __init__(self, events=None):
        self._events = events or []

    def provider_name(self):
        return "Fake"

    def is_configured(self):
        return True

    def get_odds(self, league, date):
        return self._events


def make_event(**overrides):
    defaults = dict(
        provider="sportsgameodds", event_id="evt_1", league="MLB",
        home_team="COL", away_team="LAD", game_time_utc="2026-08-18T00:40:00Z",
        retrieved_at="2026-08-18T02:00:00+00:00",
        books=[
            BookLine(book="draftkings", home_moneyline=150, away_moneyline=-175, total=11.5, home_run_line=1.5, away_run_line=-1.5),
            BookLine(book="fanduel", home_moneyline=146, away_moneyline=-174, total=11.5, home_run_line=1.5, away_run_line=-1.5),
        ],
    )
    defaults.update(overrides)
    return NormalizedGameOdds(**defaults)


def save_prior_pregame_snapshot(tmp_path, game_id="g1", total=11.5, home_ml=150, away_ml=-174, generated_at="2026-08-17T20:00:00+00:00"):
    doc = {
        "slate_date": "2026-08-17", "generated_at": generated_at,
        "games": [
            {
                "game_id": game_id,
                "vegas": {
                    "game_id": game_id, "home_team": "COL", "away_team": "LAD",
                    "provider_name": "SportsGameOdds", "is_mock": False, "retrieved_at": generated_at,
                    "current_home": {"moneyline": home_ml, "run_line": 1.5, "run_line_odds": None, "total": total},
                    "current_away": {"moneyline": away_ml, "run_line": -1.5, "run_line_odds": None, "total": total},
                    "home_implied_runs": 5.0, "away_implied_runs": 6.5,
                    "implied_runs_is_valid": True,
                    "game_status": "PREGAME", "is_frozen_pregame": False, "vegas_projection_status": "LIVE_PREGAME",
                },
            }
        ],
    }
    ge_storage.save_environment_report(doc, output_root=tmp_path)


# ----------------------------------------------------------------------------
# Classification -> game_status / vegas_projection_status
# ----------------------------------------------------------------------------


def test_pregame_status_returns_live_current_data(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")

    assert snapshot.game_status == "PREGAME"
    assert snapshot.vegas_projection_status == "LIVE_PREGAME"
    assert snapshot.is_frozen_pregame is False
    assert snapshot.current_home.total == 11.5
    assert snapshot.home_implied_runs is not None


def test_in_play_status_with_no_prior_pregame_snapshot_gives_zero_contribution(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")

    assert snapshot.game_status == "IN_PLAY"
    assert snapshot.vegas_projection_status == "IN_PLAY_ONLY"
    assert snapshot.home_implied_runs is None
    assert snapshot.away_implied_runs is None
    assert snapshot.implied_runs_is_valid is False
    assert any("pregame" in w.lower() for w in snapshot.validation_warnings)


def test_final_status_with_no_prior_pregame_snapshot_gives_zero_contribution(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Final")

    assert snapshot.game_status == "FINAL"
    assert snapshot.vegas_projection_status == "MISSING"
    assert snapshot.home_implied_runs is None


def test_unknown_status_with_no_prior_pregame_snapshot_gives_zero_contribution(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Postponed")

    assert snapshot.game_status == "UNKNOWN"
    assert snapshot.vegas_projection_status == "MISSING"
    assert snapshot.home_implied_runs is None


# ----------------------------------------------------------------------------
# Freeze behavior
# ----------------------------------------------------------------------------


def test_in_play_with_prior_valid_pregame_snapshot_freezes_to_it(tmp_path):
    save_prior_pregame_snapshot(tmp_path)
    # Current live fetch: extreme in-play pricing (game underway).
    live_event = make_event(
        books=[BookLine(book="draftkings", home_moneyline=5000, away_moneyline=-10000, total=12.5, home_run_line=7.5, away_run_line=-7.5)]
    )
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[live_event]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")

    assert snapshot.vegas_projection_status == "PREGAME_FROZEN"
    assert snapshot.is_frozen_pregame is True
    # Frozen values are the ORIGINAL pregame numbers, not the live blowout pricing.
    assert snapshot.current_home.total == 11.5
    assert snapshot.home_implied_runs == 5.0
    assert snapshot.away_implied_runs == 6.5
    assert snapshot.retrieved_at == "2026-08-17T20:00:00+00:00"  # original capture time preserved


def test_final_with_prior_valid_pregame_snapshot_freezes_to_it(tmp_path):
    save_prior_pregame_snapshot(tmp_path)
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Final")

    assert snapshot.vegas_projection_status == "PREGAME_FROZEN"
    assert snapshot.away_implied_runs == 6.5


def test_frozen_snapshot_never_overwritten_by_a_second_in_play_refresh(tmp_path):
    save_prior_pregame_snapshot(tmp_path)
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)

    first = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")
    second = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")

    assert first.home_implied_runs == second.home_implied_runs == 5.0
    assert first.retrieved_at == second.retrieved_at


def test_mock_snapshot_cannot_become_frozen_pregame(tmp_path):
    mock_doc = {
        "slate_date": "2026-08-17", "generated_at": "2026-08-17T20:00:00+00:00",
        "games": [
            {
                "game_id": "g1",
                "vegas": {
                    "game_id": "g1", "home_team": "COL", "away_team": "LAD",
                    "provider_name": "MOCK VEGAS", "is_mock": True, "retrieved_at": "2026-08-17T20:00:00+00:00",
                    "current_home": {"total": 9.0}, "current_away": {"total": 9.0},
                    "home_implied_runs": 4.5, "away_implied_runs": 4.5, "implied_runs_is_valid": True,
                    "game_status": "PREGAME", "is_frozen_pregame": False, "vegas_projection_status": "LIVE_PREGAME",
                },
            }
        ],
    }
    ge_storage.save_environment_report(mock_doc, output_root=tmp_path)

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")

    assert snapshot.vegas_projection_status != "PREGAME_FROZEN"
    assert snapshot.home_implied_runs is None


def test_invalid_pregame_snapshot_cannot_become_frozen_pregame(tmp_path):
    invalid_doc = {
        "slate_date": "2026-08-17", "generated_at": "2026-08-17T20:00:00+00:00",
        "games": [
            {
                "game_id": "g1",
                "vegas": {
                    "game_id": "g1", "home_team": "COL", "away_team": "LAD",
                    "provider_name": "SportsGameOdds", "is_mock": False, "retrieved_at": "2026-08-17T20:00:00+00:00",
                    "current_home": {"total": 11.5}, "current_away": {"total": 11.5},
                    "home_implied_runs": None, "away_implied_runs": None, "implied_runs_is_valid": False,
                    "game_status": "PREGAME", "is_frozen_pregame": False, "vegas_projection_status": "INVALID",
                },
            }
        ],
    }
    ge_storage.save_environment_report(invalid_doc, output_root=tmp_path)

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")

    assert snapshot.vegas_projection_status != "PREGAME_FROZEN"
    assert snapshot.home_implied_runs is None


# ----------------------------------------------------------------------------
# Dodgers extreme in-play regression (Milestone 24's live validation finding)
# ----------------------------------------------------------------------------


def test_dodgers_extreme_in_play_pricing_never_reaches_projection(tmp_path):
    """Milestone 24 live validation found LAD @ COL with LAD approximately
    -10000 and COL approximately +3300 -- legitimate LIVE odds,
    inappropriate for pregame DFS projection context. This must never
    happen again: get_vegas_line() must return the frozen pregame value,
    never the in-play blowout pricing."""
    save_prior_pregame_snapshot(tmp_path, home_ml=150, away_ml=-174, total=11.5)  # genuine pregame line
    live_blowout_event = make_event(
        books=[BookLine(book="draftkings", home_moneyline=3300, away_moneyline=-10000, total=12.5, home_run_line=8.5, away_run_line=-8.5)]
    )
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[live_blowout_event]), snapshot_root=tmp_path)

    projection_snapshot = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")
    assert projection_snapshot.current_home.moneyline == 150  # frozen pregame, NOT 3300
    assert projection_snapshot.current_away.moneyline == -174  # frozen pregame, NOT -10000
    assert projection_snapshot.is_frozen_pregame is True

    # The live blowout data is still available for RESEARCH/HISTORY display,
    # just via a separate method never consumed by Native/AI projections.
    live_snapshot = provider.get_live_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")
    assert live_snapshot.current_home.moneyline == 3300
    assert live_snapshot.current_away.moneyline == -10000
    assert live_snapshot.game_status == "IN_PLAY"


# ----------------------------------------------------------------------------
# get_live_vegas_line() always returns current data
# ----------------------------------------------------------------------------


def test_get_live_vegas_line_returns_current_data_even_when_pregame(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    live = provider.get_live_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert live.game_status == "PREGAME"
    assert live.current_home.total == 11.5


def test_get_live_vegas_line_never_freezes(tmp_path):
    save_prior_pregame_snapshot(tmp_path)
    live_event = make_event(
        books=[BookLine(book="draftkings", home_moneyline=5000, away_moneyline=-10000, total=12.5)]
    )
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[live_event]), snapshot_root=tmp_path)
    live = provider.get_live_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")
    assert live.is_frozen_pregame is False
    assert live.current_home.moneyline == 5000


# ----------------------------------------------------------------------------
# get_projection_vegas_snapshot() public helper
# ----------------------------------------------------------------------------


def test_get_projection_vegas_snapshot_returns_last_valid_pregame(tmp_path):
    save_prior_pregame_snapshot(tmp_path)
    result = get_projection_vegas_snapshot("g1", "2026-08-17", snapshot_root=tmp_path)
    assert result is not None
    assert result.away_implied_runs == 6.5


def test_get_projection_vegas_snapshot_returns_none_when_never_captured(tmp_path):
    result = get_projection_vegas_snapshot("g1", "2026-08-17", snapshot_root=tmp_path)
    assert result is None


# ----------------------------------------------------------------------------
# Doubleheaders -- independent game_ids resolve independently
# ----------------------------------------------------------------------------


def test_doubleheader_games_resolve_pregame_lock_independently(tmp_path):
    save_prior_pregame_snapshot(tmp_path, game_id="g1_game1", total=9.0, generated_at="2026-08-17T18:00:00+00:00")
    # g1_game2 (second game of the doubleheader) never captured a pregame snapshot.
    event_game2 = make_event(event_id="evt_2")
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[event_game2]), snapshot_root=tmp_path)

    frozen_for_game1 = get_projection_vegas_snapshot("g1_game1", "2026-08-17", snapshot_root=tmp_path)
    assert frozen_for_game1 is not None

    game2_result = provider.get_vegas_line("g1_game2", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")
    assert game2_result.vegas_projection_status == "IN_PLAY_ONLY"
    assert game2_result.home_implied_runs is None
