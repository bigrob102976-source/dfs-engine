import pytest

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.draftkings_csv_provider import DraftKingsCsvProvider
from dfs.providers.draftkings_csv_storage import save_upload

HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"


def _csv(rows: str) -> bytes:
    return (HEADER + rows).encode("utf-8")


MAIN_CSV = _csv(
    "P,Ace Pitcher (101),Ace Pitcher,101,P,9500,TOR@BOS 7:05PM ET,TOR,22.1\n"
    "OF,Lead Off (102),Lead Off,102,OF,4200,TOR@BOS 7:05PM ET,BOS,9.4\n"
)

TURBO_CSV = _csv(
    "P,Turbo Ace (201),Turbo Ace,201,P,10200,NYY@BAL 7:05PM ET,NYY,25.0\n"
)


def test_raises_unavailable_when_no_uploads_exist(tmp_path):
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-14")


def test_builds_one_slate_per_uploaded_label(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    save_upload(TURBO_CSV, "2026-08-14", "Turbo", "DKSalariesTurbo.csv", output_root=tmp_path)

    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")

    assert len(result.slates) == 2
    names = {s.slate_name for s in result.slates}
    assert names == {"Main", "Turbo"}
    assert result.source == "draftkings_csv"


def test_real_salaries_and_identity_from_csv_never_invented(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")
    main_slate_id = next(s.slate_id for s in result.slates if s.slate_name == "Main")
    players = {p.name: p for p in result.players_by_slate[main_slate_id]}

    assert players["Ace Pitcher"].salary == 9500
    assert players["Ace Pitcher"].team == "TOR"
    assert players["Ace Pitcher"].opponent == "BOS"
    assert players["Ace Pitcher"].position_eligibility == ["P"]
    assert players["Ace Pitcher"].external_player_id == "101"
    assert players["Ace Pitcher"].source == "draftkings_csv"


def test_only_the_newest_upload_per_label_is_used(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries_old.csv", output_root=tmp_path, uploaded_at="2026-08-14T18:00:00Z")
    newer_csv = _csv("P,New Ace (999),New Ace,999,P,8800,TOR@BOS 7:05PM ET,TOR,19.0\n")
    save_upload(newer_csv, "2026-08-14", "Main", "DKSalaries_new.csv", output_root=tmp_path, uploaded_at="2026-08-14T18:00:01Z")

    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")

    assert len(result.slates) == 1
    players = result.players_by_slate[result.slates[0].slate_id]
    assert {p.name for p in players} == {"New Ace"}


def test_malformed_upload_is_skipped_with_a_warning_not_a_crash(tmp_path):
    save_upload(b"not,a,dk,csv\n1,2,3,4\n", "2026-08-14", "Bad", "bad.csv", output_root=tmp_path)
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)

    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")

    assert len(result.slates) == 1
    assert result.slates[0].slate_name == "Main"
    assert any("Bad" in w for w in result.warnings)


def test_raises_unavailable_when_every_upload_is_malformed(tmp_path):
    save_upload(b"not,a,dk,csv\n1,2,3,4\n", "2026-08-14", "Bad", "bad.csv", output_root=tmp_path)
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    with pytest.raises(ProviderUnavailableError):
        provider.get_slate("2026-08-14")


def test_rejects_non_mlb_sport(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    with pytest.raises(ProviderNoSlateError):
        provider.get_slate("2026-08-14", sport="NFL")


def test_implements_interface():
    assert isinstance(DraftKingsCsvProvider(dfs_input_root="unused"), DFSSalaryProvider)


# ----------------------------------------------------------------------------
# game_ids / player_count (Milestone 26)
# ----------------------------------------------------------------------------


def test_game_ids_empty_when_no_research_games_passed(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")
    assert result.slates[0].game_ids == []


def test_game_ids_resolved_when_research_games_passed(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    save_upload(TURBO_CSV, "2026-08-14", "Turbo", "DKSalariesTurbo.csv", output_root=tmp_path)
    research_games = [
        {"game_id": "g-main", "away_team_abbr": "TOR", "home_team_abbr": "BOS", "game_datetime_utc": "2026-08-14T23:05:00Z"},
        {"game_id": "g-turbo", "away_team_abbr": "NYY", "home_team_abbr": "BAL", "game_datetime_utc": "2026-08-14T23:05:00Z"},
    ]

    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14", research_games=research_games)

    by_name = {s.slate_name: s for s in result.slates}
    assert by_name["Main"].game_ids == ["g-main"]
    assert by_name["Turbo"].game_ids == ["g-turbo"]
    # No cross-slate leakage: Main never resolves Turbo's game and vice versa.
    assert "g-turbo" not in by_name["Main"].game_ids
    assert "g-main" not in by_name["Turbo"].game_ids


def test_player_count_matches_dk_row_count(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")
    assert result.slates[0].player_count == 2  # Ace Pitcher + Lead Off


def test_realistic_upload_is_classified_official_user_upload(tmp_path):
    save_upload(MAIN_CSV, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")
    assert result.slates[0].source_provenance == "OFFICIAL_USER_UPLOAD"
    assert result.slates[0].realism_blocked is False


def test_impossible_pitcher_count_upload_is_reclassified_synthetic(tmp_path):
    # Modeled on the real 2026-08-18 LAD case this milestone traced:
    # dozens of pitcher-eligible rows salaried for one team in one game.
    rows = "".join(
        f"RP,Pitcher {i} ({100 + i}),Pitcher {i},{100 + i},RP,4000,TOR@BOS 7:05PM ET,TOR,5.0\n" for i in range(25)
    )
    rows += "OF,Lead Off (999),Lead Off,999,OF,4200,TOR@BOS 7:05PM ET,BOS,9.4\n"
    synthetic_csv = _csv(rows)
    save_upload(synthetic_csv, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)

    provider = DraftKingsCsvProvider(dfs_input_root=str(tmp_path))
    result = provider.get_slate("2026-08-14")

    assert result.slates[0].source_provenance == "SYNTHETIC_VALIDATION"
    assert result.slates[0].realism_blocked is True
    assert result.slates[0].realism_findings  # never blocked silently -- reasons are recorded
    assert any("SYNTHETIC_VALIDATION" in w for w in result.warnings)
