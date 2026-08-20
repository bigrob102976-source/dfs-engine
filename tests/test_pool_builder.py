import json
from pathlib import Path

import pytest

from dfs.models import DKSalaryRow
from dfs.pool_builder import UnsafeSourceProvenanceError, build_pool, print_pool_report, save_pool
from dfs.providers.adapter import provider_players_to_dk_rows


def _write_research_package(root: Path, date: str):
    folder = root / date
    folder.mkdir(parents=True)
    games = [{
        "game_id": "g1", "date": date, "game_datetime_utc": "2026-08-11T23:05:00Z", "status": "scheduled",
        "home_team_id": "1", "home_team_abbr": "BOS", "away_team_id": "2", "away_team_abbr": "TOR",
        "venue_id": "v1", "venue_name": "Fenway", "home_probable_pitcher_id": "p2", "away_probable_pitcher_id": "p1",
        "game_number": 1,
    }]
    teams = [
        {"team_id": "1", "abbreviation": "BOS", "name": "Boston Red Sox"},
        {"team_id": "2", "abbreviation": "TOR", "name": "Toronto Blue Jays"},
    ]
    pitchers = [
        {"player_id": "p1", "name": "Away Ace", "team_id": "2", "team_abbr": "TOR", "opponent_team_id": "1",
         "opponent_abbr": "BOS", "game_id": "g1", "throws": "R", "status": "probable", "source": "mlb_stats_api"},
    ]
    batters = [
        {"player_id": "h1", "name": "Leadoff Hitter", "team_id": "1", "team_abbr": "BOS", "opponent_team_id": "2",
         "opponent_abbr": "TOR", "game_id": "g1", "batting_order": 1, "position": "CF", "bats": "L",
         "status": "starting_lineup", "source": "mlb_stats_api"},
    ]
    (folder / "games.json").write_text(json.dumps(games), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps(teams), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps(pitchers), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps(batters), encoding="utf-8")


def _dk_rows():
    return [
        DKSalaryRow(dk_player_id="d1", name="Away Ace", team_abbrev="TOR", dk_positions=["P"], salary=8000, game_info="TOR@BOS 7:05PM ET"),
        DKSalaryRow(dk_player_id="d2", name="Leadoff Hitter", team_abbrev="BOS", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET"),
    ]


def test_build_pool_matches_real_identities(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")

    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    assert result.report["matched_to_mlb"] == 2
    # No pitcher/batter snapshot exists in this fixture -- matched players
    # correctly land as "missing_projection", not "active" (never invented).
    assert {p.name for p in result.players} == {"Away Ace", "Leadoff Hitter"}
    assert all(p.match_status == "matched" for p in result.players)
    assert all(p.lineup_status == "missing_projection" for p in result.players)


def test_build_pool_never_invents_projection_without_a_snapshot(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    assert all(p.projection is None for p in result.players)


def test_save_pool_is_immutable(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    dfs_input_root = tmp_path / "dfs_input"
    generated_at = "2026-08-11T18:00:00+00:00"
    pool_path, report_path = save_pool(result, "2026-08-11", str(dfs_input_root), generated_at=generated_at)
    assert pool_path.exists()
    assert report_path.exists()

    with pytest.raises(FileExistsError):
        save_pool(result, "2026-08-11", str(dfs_input_root), generated_at=generated_at)


def test_save_pool_records_extra_metadata(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    pool_path, _ = save_pool(
        result, "2026-08-11", str(tmp_path / "dfs_input"),
        extra_metadata={"provider_source": "mock_dev_provider", "selected_slate_id": "mock-main"},
        generated_at="2026-08-11T18:00:00+00:00",
    )
    doc = json.loads(pool_path.read_text(encoding="utf-8"))
    assert doc["provider_source"] == "mock_dev_provider"
    assert doc["selected_slate_id"] == "mock-main"


def test_print_pool_report_does_not_crash(tmp_path, capsys):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    print_pool_report(result)
    captured = capsys.readouterr()
    assert "Matched to MLB" in captured.out
    assert "Roster feasibility" in captured.out


def test_build_pool_reports_identity_integrity_summary(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    integrity = result.report["identity_integrity"]
    assert integrity["total"] == 2
    assert integrity["invalid"] == 0
    assert integrity["invalid_rows"] == []
    assert len(result.integrity_results) == 2


def _blocked_realism_dk_rows():
    # 20 pitcher-eligible TOR rows in one game -- well past
    # MAX_PLAUSIBLE_PITCHERS_PER_TEAM_BLOCK (18), same shape as the real
    # 2026-08-18 LAD case this milestone investigated.
    rows = [DKSalaryRow(dk_player_id="d1", name="Away Ace", team_abbrev="TOR", dk_positions=["P"], salary=8000,
                         game_info="TOR@BOS 7:05PM ET")]
    for i in range(20):
        rows.append(DKSalaryRow(dk_player_id=f"p{i}", name=f"Extra Pitcher {i}", team_abbrev="TOR",
                                 dk_positions=["RP"], salary=4000, game_info="TOR@BOS 7:05PM ET"))
    rows.append(DKSalaryRow(dk_player_id="d2", name="Leadoff Hitter", team_abbrev="BOS", dk_positions=["OF"],
                             salary=4000, game_info="TOR@BOS 7:05PM ET"))
    return rows


def test_build_pool_without_a_provenance_claim_never_blocks(tmp_path):
    # Backward compatibility: every caller that predates Milestone 27.4
    # (including every other test in this file) doesn't pass
    # source_provenance_claim, so the guard must never activate for them
    # even when the content would otherwise fail realism checks.
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_blocked_realism_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    assert result.report["source_provenance"] == "SYNTHETIC_VALIDATION"
    assert result.report["source_realism"]["blocked"] is True


def test_build_pool_rejects_synthetic_source_claimed_as_official_upload(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    with pytest.raises(UnsafeSourceProvenanceError):
        build_pool(
            _blocked_realism_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"),
            source_provenance_claim="OFFICIAL_USER_UPLOAD",
        )


def test_build_pool_rejects_synthetic_source_claimed_as_mock(tmp_path):
    # DEVELOPMENT_MOCK is equally not in TRUSTED_FOR_PRODUCTION, so a mock
    # provider's claim doesn't grant an exemption from the realism guard.
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    with pytest.raises(UnsafeSourceProvenanceError):
        build_pool(
            _blocked_realism_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"),
            source_provenance_claim="DEVELOPMENT_MOCK",
        )


def test_build_pool_permits_synthetic_source_in_dev_mode(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(
        _blocked_realism_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"),
        source_provenance_claim="OFFICIAL_USER_UPLOAD", dev_mode=True,
    )
    assert result.report["source_provenance"] == "SYNTHETIC_VALIDATION"


def test_build_pool_accepts_clean_official_upload_source(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(
        _dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"),
        source_provenance_claim="OFFICIAL_USER_UPLOAD",
    )
    assert result.report["source_provenance"] == "OFFICIAL_USER_UPLOAD"
    assert result.report["source_realism"]["blocked"] is False


def test_build_pool_excludes_il_status_player_and_reports_it(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    rows = _dk_rows()
    rows[1].dk_status = "IL"  # Leadoff Hitter -- a confirmed starter, but DK flags them IL

    result = build_pool(rows, "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    hitter = next(p for p in result.players if p.name == "Leadoff Hitter")
    assert hitter.eligibility_status == "STARTING_HITTER"  # still a real confirmed starter...
    assert hitter.optimizer_eligible is False  # ...but excluded by the IL rule
    assert result.report["availability_filter"]["dropped_count"] == 1
    assert result.report["availability_filter"]["excluded"][0]["reason"] == "DK Status = IL"
    assert hitter not in result.active_pool


def test_build_pool_flags_dtd_without_excluding(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    rows = _dk_rows()
    rows[1].dk_status = "DTD"

    result = build_pool(rows, "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    hitter = next(p for p in result.players if p.name == "Leadoff Hitter")
    assert hitter.optimizer_eligible is True
    assert "DTD" in hitter.tags
    assert result.report["availability_filter"]["dropped_count"] == 0


def test_build_pool_exclusion_rules_are_toggleable(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    rows = _dk_rows()
    rows[1].dk_status = "IL"

    result = build_pool(rows, "2026-08-11", str(research_root), str(tmp_path / "predictions"), exclude_il=False)

    hitter = next(p for p in result.players if p.name == "Leadoff Hitter")
    assert hitter.optimizer_eligible is True
    assert result.report["availability_filter"]["dropped_count"] == 0


def test_build_pool_reports_teams_awaiting_lineups(tmp_path):
    # TOR has no batter research records at all -- its lineup hasn't
    # posted -- while BOS's has (per _write_research_package).
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    rows = _dk_rows() + [
        DKSalaryRow(dk_player_id="d3", name="TOR Hitter", team_abbrev="TOR", dk_positions=["OF"], salary=4000, game_info="TOR@BOS 7:05PM ET"),
    ]

    result = build_pool(rows, "2026-08-11", str(research_root), str(tmp_path / "predictions"))

    assert result.report["teams_awaiting_lineups"] == ["TOR"]


def test_build_pool_no_teams_awaiting_lineups_when_all_posted(tmp_path):
    research_root = tmp_path / "research_output"
    _write_research_package(research_root, "2026-08-11")
    result = build_pool(_dk_rows(), "2026-08-11", str(research_root), str(tmp_path / "predictions"))
    assert result.report["teams_awaiting_lineups"] == []


def test_provider_players_to_dk_rows_conversion():
    provider_players = [
        {"external_player_id": "mock-1", "name": "X", "team": "AAA", "salary": 5000,
         "position_eligibility": ["1B", "OF"], "game": "AAA@BBB 7:05PM ET"},
    ]
    rows = provider_players_to_dk_rows(provider_players)
    assert len(rows) == 1
    row = rows[0]
    assert row.dk_player_id == "mock-1"
    assert row.team_abbrev == "AAA"
    assert row.dk_positions == ["1B", "OF"]
    assert row.salary == 5000
    assert row.game_info == "AAA@BBB 7:05PM ET"
    assert row.avg_points_per_game is None  # never invented


def test_provider_players_to_dk_rows_handles_missing_optional_fields():
    rows = provider_players_to_dk_rows([{"external_player_id": "mock-1", "name": "X", "team": "AAA", "salary": 5000}])
    assert rows[0].dk_positions == []
    assert rows[0].game_info == ""
