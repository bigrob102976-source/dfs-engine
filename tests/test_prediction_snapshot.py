import json

import pytest

from config.scoring_config import PITCHER_MODEL_VERSION
from models.pitcher import PitcherBoardEntry, PitcherInput, SeasonStats
from research.prediction_snapshot import (
    build_snapshot,
    list_snapshots,
    load_latest_snapshot,
    load_snapshot,
    save_snapshot,
    timestamp_tag,
)
from research.quality_report import build_quality_report


def _entry(pid, name, overall=60.0):
    return PitcherBoardEntry(
        player_id=pid, name=name, team="AAA", opponent="BBB",
        projection=20.0, ceiling=28.0, floor=12.0,
        overall_score=overall, strikeout_score=70.0, run_prevention_score=60.0,
        matchup_score=55.0, workload_score=65.0, contact_score=50.0,
        environment_score=50.0, value_score=50.0,
        risk_score=35.0, confidence=60.0,
        tags=["elite_csw"], reasons=["some reason"],
    )


def _pitcher(pid, name):
    return PitcherInput(
        player_id=pid, name=name, team="AAA", opponent="BBB",
        game_id=f"game-{pid}", venue_name="Test Park",
        season=SeasonStats(k_percent=25.0),
    )


def _board_and_pitchers(n):
    entries = [_entry(str(i), f"Pitcher {i}") for i in range(n)]
    pitchers_by_id = {str(i): _pitcher(str(i), f"Pitcher {i}") for i in range(n)}
    return entries, pitchers_by_id


def test_build_snapshot_includes_required_top_level_fields():
    board, pitchers_by_id = _board_and_pitchers(3)
    quality_report = build_quality_report(list(pitchers_by_id.values()))
    snapshot = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {"mlb_stats_sources": ["x"]}, generated_at="2026-08-11T16:55:00+00:00")

    assert snapshot["slate_date"] == "2026-08-11"
    assert snapshot["generated_at"] == "2026-08-11T16:55:00+00:00"
    assert snapshot["model_version"] == PITCHER_MODEL_VERSION
    assert "research_package_version" in snapshot
    assert snapshot["source_metadata"] == {"mlb_stats_sources": ["x"]}
    assert "research_quality_report" in snapshot


def test_build_snapshot_preserves_every_pitcher_not_just_top_n():
    board, pitchers_by_id = _board_and_pitchers(25)  # more than any "top 10" display cap
    quality_report = build_quality_report(list(pitchers_by_id.values()))
    snapshot = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {})

    assert snapshot["pitcher_count"] == 25
    assert len(snapshot["pitchers"]) == 25
    assert {p["player_id"] for p in snapshot["pitchers"]} == {str(i) for i in range(25)}


def test_build_snapshot_pitcher_record_has_all_required_fields():
    board, pitchers_by_id = _board_and_pitchers(1)
    quality_report = build_quality_report(list(pitchers_by_id.values()))
    snapshot = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {})
    record = snapshot["pitchers"][0]

    for field in [
        "player_id", "name", "team", "opponent", "game_id", "venue",
        "projection", "ceiling", "floor",
        "overall_score", "strikeout_score", "run_prevention_score", "matchup_score",
        "workload_score", "contact_score", "environment_score", "value_score",
        "risk_score", "confidence", "tags", "reasons",
        "season_metrics", "recent_metrics", "trend_metrics", "opponent_metrics", "data_status",
    ]:
        assert field in record, f"missing field: {field}"
    assert record["game_id"] == "game-0"
    assert record["venue"] == "Test Park"
    assert record["season_metrics"]["k_percent"] == 25.0


def test_save_snapshot_writes_to_predictions_date_folder(tmp_path):
    board, pitchers_by_id = _board_and_pitchers(2)
    quality_report = build_quality_report(list(pitchers_by_id.values()))
    snapshot = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {}, generated_at="2026-08-11T16:55:00+00:00")

    path = save_snapshot(snapshot, output_root=tmp_path)

    assert path == tmp_path / "2026-08-11" / "pitcher_board_20260811T165500.json"
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["slate_date"] == "2026-08-11"


def test_save_snapshot_never_overwrites_existing_file(tmp_path):
    board, pitchers_by_id = _board_and_pitchers(1)
    quality_report = build_quality_report(list(pitchers_by_id.values()))
    snapshot = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {}, generated_at="2026-08-11T16:55:00+00:00")

    save_snapshot(snapshot, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_snapshot(snapshot, output_root=tmp_path)  # same generated_at -> same filename


def test_multiple_runs_same_day_create_separate_snapshots(tmp_path):
    board, pitchers_by_id = _board_and_pitchers(1)
    quality_report = build_quality_report(list(pitchers_by_id.values()))

    morning = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {}, generated_at="2026-08-11T13:00:00+00:00")
    afternoon = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {}, generated_at="2026-08-11T20:00:00+00:00")

    morning_path = save_snapshot(morning, output_root=tmp_path)
    afternoon_path = save_snapshot(afternoon, output_root=tmp_path)

    assert morning_path != afternoon_path
    assert morning_path.exists() and afternoon_path.exists()
    assert len(list_snapshots("2026-08-11", output_root=tmp_path)) == 2


def test_load_latest_snapshot_picks_most_recent(tmp_path):
    board, pitchers_by_id = _board_and_pitchers(1)
    quality_report = build_quality_report(list(pitchers_by_id.values()))

    for hour in ("13", "16", "20"):
        snap = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {}, generated_at=f"2026-08-11T{hour}:00:00+00:00")
        save_snapshot(snap, output_root=tmp_path)

    latest = load_latest_snapshot("2026-08-11", output_root=tmp_path)
    assert latest["generated_at"] == "2026-08-11T20:00:00+00:00"


def test_load_latest_snapshot_raises_when_none_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest_snapshot("2026-08-11", output_root=tmp_path)


def test_load_snapshot_round_trips(tmp_path):
    board, pitchers_by_id = _board_and_pitchers(2)
    quality_report = build_quality_report(list(pitchers_by_id.values()))
    snapshot = build_snapshot("2026-08-11", board, pitchers_by_id, quality_report, {}, generated_at="2026-08-11T16:55:00+00:00")
    path = save_snapshot(snapshot, output_root=tmp_path)

    loaded = load_snapshot(path)
    assert loaded == snapshot


def test_timestamp_tag_matches_milestone_example():
    assert timestamp_tag("2026-08-11T16:55:00+00:00") == "20260811T165500"
