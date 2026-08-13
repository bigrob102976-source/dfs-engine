import json
import urllib.error

import pytest

from research import collector, normalizer, validator
from research.engine import build_research_package
from research.models import Game, PitcherRecord

# ----------------------------------------------------------------------------
# Fixture data shaped like (a small subset of) the real MLB Stats API
# schedule response, so normalizer/validator/engine tests never touch the
# network. Game 111 has full data (probable pitchers + lineups posted);
# game 112 deliberately has a TBD away probable pitcher and no lineups yet,
# to exercise the "tolerate missing data, warn, don't crash" paths.
# ----------------------------------------------------------------------------

FIXTURE_SCHEDULE = {
    "dates": [
        {
            "date": "2026-08-11",
            "games": [
                {
                    "gamePk": 111,
                    "gameDate": "2026-08-11T23:00:00Z",
                    "officialDate": "2026-08-11",
                    "status": {"detailedState": "Pre-Game"},
                    "gameNumber": 1,
                    "venue": {"id": 5, "name": "Test Park"},
                    "teams": {
                        "away": {
                            "team": {
                                "id": 10, "abbreviation": "AAA", "name": "Alpha Athletics",
                                "league": {"name": "American League"}, "division": {"name": "AL East"},
                            },
                            "probablePitcher": {"id": 1002, "fullName": "Away Arm"},
                        },
                        "home": {
                            "team": {
                                "id": 20, "abbreviation": "BBB", "name": "Beta Bears",
                                "league": {"name": "American League"}, "division": {"name": "AL Central"},
                            },
                            "probablePitcher": {"id": 1001, "fullName": "Home Ace"},
                        },
                    },
                    "lineups": {
                        "homePlayers": [
                            {"id": 2001, "fullName": "Home Batter One", "primaryPosition": {"abbreviation": "C"}},
                            {"id": 2002, "fullName": "Home Batter Two", "primaryPosition": {"abbreviation": "1B"}},
                        ],
                        "awayPlayers": [
                            {"id": 3001, "fullName": "Away Batter One", "primaryPosition": {"abbreviation": "CF"}},
                            {"id": 3002, "fullName": "Away Batter Two", "primaryPosition": {"abbreviation": "SS"}},
                        ],
                    },
                },
                {
                    "gamePk": 112,
                    "gameDate": "2026-08-11T20:00:00Z",
                    "officialDate": "2026-08-11",
                    "status": {"detailedState": "Pre-Game"},
                    "gameNumber": 1,
                    "venue": {"id": 6, "name": "Other Park"},
                    "teams": {
                        "away": {
                            "team": {
                                "id": 20, "abbreviation": "BBB", "name": "Beta Bears",
                                "league": {"name": "American League"}, "division": {"name": "AL Central"},
                            },
                            # no probablePitcher: TBD
                        },
                        "home": {
                            "team": {
                                "id": 30, "abbreviation": "CCC", "name": "Gamma Giants",
                                "league": {"name": "National League"}, "division": {"name": "NL West"},
                            },
                            "probablePitcher": {"id": 1003, "fullName": "Home Newcomer"},
                        },
                    },
                    # no "lineups" key at all: not posted yet
                },
            ],
        }
    ]
}

FIXTURE_PEOPLE = {
    "1001": {"id": 1001, "fullName": "Home Ace", "pitchHand": {"code": "R"}},
    "1002": {"id": 1002, "fullName": "Away Arm", "pitchHand": {"code": "L"}},
    # 1003 intentionally missing to exercise the "no bio info available" path
}


# ----------------------------------------------------------------------------
# Normalizer tests
# ----------------------------------------------------------------------------


def test_normalize_games_extracts_expected_fields():
    warnings = []
    games, teams_by_id = normalizer.normalize_games(FIXTURE_SCHEDULE, warnings)

    assert len(games) == 2
    assert set(teams_by_id.keys()) == {"10", "20", "30"}

    game_111 = next(g for g in games if g.game_id == "111")
    assert game_111.home_team_abbr == "BBB"
    assert game_111.away_team_abbr == "AAA"
    assert game_111.venue_name == "Test Park"
    assert game_111.home_probable_pitcher_id == "1001"
    assert game_111.away_probable_pitcher_id == "1002"

    game_112 = next(g for g in games if g.game_id == "112")
    assert game_112.away_probable_pitcher_id is None
    assert any("away probable pitcher not yet announced" in w for w in warnings)


def test_normalize_pitchers_includes_throws_from_people():
    warnings = []
    pitchers = normalizer.normalize_pitchers(FIXTURE_SCHEDULE, FIXTURE_PEOPLE, warnings)

    assert len(pitchers) == 3
    by_id = {p.player_id: p for p in pitchers}
    assert by_id["1001"].throws == "R"
    assert by_id["1002"].throws == "L"
    assert by_id["1003"].throws is None
    assert any("no bio info available" in w for w in warnings)

    # opponent linkage is correct in both directions
    assert by_id["1001"].opponent_team_id == "10"  # home pitcher (team 20) faces away team 10
    assert by_id["1002"].opponent_team_id == "20"  # away pitcher (team 10) faces home team 20


def test_normalize_batters_reads_lineup_order():
    warnings = []
    batters = normalizer.normalize_batters(FIXTURE_SCHEDULE, warnings)

    assert len(batters) == 4  # only game 111 has lineups posted
    assert all(b.game_id == "111" for b in batters)

    home_batters = sorted((b for b in batters if b.team_id == "20"), key=lambda b: b.batting_order)
    assert [b.name for b in home_batters] == ["Home Batter One", "Home Batter Two"]
    assert [b.batting_order for b in home_batters] == [1, 2]

    assert any("starting lineups not yet available" in w for w in warnings)


# ----------------------------------------------------------------------------
# Validator tests
# ----------------------------------------------------------------------------


def _bare_game(game_id: str) -> Game:
    return Game(
        game_id=game_id, date="2026-08-11", game_datetime_utc=None, status="Pre-Game",
        home_team_id="20", home_team_abbr="BBB", away_team_id="10", away_team_abbr="AAA",
    )


def test_validator_flags_duplicate_game_id():
    games = [_bare_game("111"), _bare_game("111")]
    issues = validator.validate_games(games, slate_date="2026-08-11")
    assert any(i.level == "error" and "duplicate game_id" in i.message for i in issues)


def test_validator_flags_invalid_date():
    issues = validator.validate_date("08-11-2026")
    assert len(issues) == 1
    assert issues[0].level == "error"


def test_validator_flags_duplicate_pitcher_in_same_game():
    pitchers = [
        PitcherRecord(player_id="1001", name="Dup", team_id="20", team_abbr="BBB",
                       opponent_team_id="10", opponent_abbr="AAA", game_id="111"),
        PitcherRecord(player_id="1001", name="Dup", team_id="20", team_abbr="BBB",
                       opponent_team_id="10", opponent_abbr="AAA", game_id="111"),
    ]
    issues = validator.validate_pitchers(pitchers, known_team_ids={"20", "10"}, known_game_ids={"111"})
    assert any("duplicate pitcher record" in i.message for i in issues)


def test_validator_flags_unknown_game_reference():
    pitchers = [
        PitcherRecord(player_id="1001", name="Ghost", team_id="20", team_abbr="BBB",
                       opponent_team_id="10", opponent_abbr="AAA", game_id="999"),
    ]
    issues = validator.validate_pitchers(pitchers, known_team_ids={"20", "10"}, known_game_ids={"111"})
    assert any(i.level == "error" and "unknown game_id" in i.message for i in issues)


# ----------------------------------------------------------------------------
# Engine (full pipeline) tests -- network calls are monkeypatched out
# ----------------------------------------------------------------------------


def test_engine_writes_all_expected_files(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "fetch_schedule", lambda date: FIXTURE_SCHEDULE)
    monkeypatch.setattr(collector, "fetch_person", lambda player_id: FIXTURE_PEOPLE.get(player_id))

    report = build_research_package("2026-08-11", output_root=str(tmp_path))

    assert report.games_found == 2
    assert report.teams_found == 3
    assert report.pitchers_found == 3
    assert report.batters_found == 4
    assert report.errors == []
    assert len(report.warnings) > 0  # TBD pitcher + missing lineups + missing bio

    folder = tmp_path / "2026-08-11"
    for name in ("games.json", "teams.json", "pitchers.json", "batters.json", "slate.json", "metadata.json"):
        path = folder / name
        assert path.exists()
        json.loads(path.read_text(encoding="utf-8"))  # must be valid JSON

    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["slate_date"] == "2026-08-11"
    assert "mlb_stats_api:schedule" in metadata["sources_used"]
    assert metadata["errors"] == []

    slate_index = json.loads((folder / "slate.json").read_text(encoding="utf-8"))
    assert slate_index["counts"] == {"games": 2, "teams": 3, "pitchers": 3, "batters": 4}
    assert slate_index["bullpens"] == []
    assert slate_index["statcast_metadata"] == []
    assert len(slate_index["notes"]) > 0  # uncollected categories are documented, not hidden


def test_engine_survives_schedule_fetch_failure(tmp_path, monkeypatch):
    def _raise(date):
        raise urllib.error.URLError("simulated network failure")

    monkeypatch.setattr(collector, "fetch_schedule", _raise)

    report = build_research_package("2026-08-11", output_root=str(tmp_path))

    assert report.games_found == 0
    assert len(report.errors) == 1
    assert "failed to fetch schedule" in report.errors[0]

    # Files are still written -- the failure is reported, not hidden.
    folder = tmp_path / "2026-08-11"
    assert (folder / "metadata.json").exists()
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["errors"]) == 1
