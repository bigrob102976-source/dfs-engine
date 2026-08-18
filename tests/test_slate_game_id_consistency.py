"""Milestone 27.2 -- central integration assertion: for one real matchup,
DK slate resolution, the Vegas snapshot, and the research package must
all agree on the SAME authoritative MLB game_id. This is the single
invariant M27.1 (Vegas event resolution) and M27.2 (player-pool
preservation) both depend on -- if it ever breaks, the two systems could
each honestly resolve the "right" event for THEIR OWN understanding of
the game and still silently disagree with each other."""

from dfs.slate_validation import resolve_game_ids
from research.game_environment.providers.base import OddsProvider
from research.game_environment.providers.models import BookLine, NormalizedGameOdds
from research.game_environment.vegas import SportsGameOddsVegasProvider


class FakeOddsProvider(OddsProvider):
    name = "fake"
    is_mock = False

    def __init__(self, events):
        self._events = events

    def provider_name(self):
        return "Fake"

    def is_configured(self):
        return True

    def get_odds(self, league, date):
        return self._events


def _research_games():
    return [
        {"game_id": "824319", "home_team_abbr": "COL", "away_team_abbr": "LAD", "game_datetime_utc": "2026-08-19T00:40:00Z", "status": "Scheduled"},
        {"game_id": "823667", "home_team_abbr": "MIN", "away_team_abbr": "ATL", "game_datetime_utc": "2026-08-18T23:40:00Z", "status": "Scheduled"},
    ]


def test_dk_resolved_game_id_matches_vegas_snapshot_game_id(tmp_path):
    games = _research_games()

    # DK's own "Game Info" string for this matchup.
    dk_game_ids = resolve_game_ids(["LAD@COL 08/18/2026 08:40PM ET"], games)
    assert dk_game_ids == ["824319"]

    # Vegas is built by the collector passing the SAME research game_id
    # in explicitly (research/game_environment/collector.py::build_game_report)
    # -- simulated here directly, since that's the real call contract.
    event = NormalizedGameOdds(
        provider="sportsgameodds", event_id="evt_today", league="MLB", home_team="COL", away_team="LAD",
        game_time_utc="2026-08-19T00:40:00.000Z", retrieved_at="2026-08-18T21:00:00+00:00",
        books=[BookLine(book="draftkings", home_moneyline=146, away_moneyline=-176, total=11.5, home_run_line=1.5, away_run_line=-1.5)],
    )
    vegas_provider = SportsGameOddsVegasProvider(FakeOddsProvider([event]), snapshot_root=tmp_path)
    snapshot = vegas_provider.get_vegas_line(
        dk_game_ids[0], "COL", "LAD", slate_date="2026-08-18", mlb_game_status="Scheduled",
        mlb_scheduled_start_utc="2026-08-19T00:40:00Z",
    )

    # THE invariant: the same game_id was used to build the Vegas
    # snapshot as the one DK's own slate resolution produced.
    assert snapshot.game_id == dk_game_ids[0] == "824319"


def test_two_different_matchups_never_share_a_resolved_game_id():
    games = _research_games()
    lad_col = resolve_game_ids(["LAD@COL 08/18/2026 08:40PM ET"], games)
    atl_min = resolve_game_ids(["ATL@MIN 08/18/2026 07:40PM ET"], games)
    assert lad_col == ["824319"]
    assert atl_min == ["823667"]
    assert lad_col != atl_min
