import json

import pytest

from config.batter_scoring_config import BATTER_MODEL_VERSION
from config.scoring_config import PITCHER_MODEL_VERSION
from evaluation.pitcher_evaluator import evaluate_slate as evaluate_pitcher_slate
from models.batter import BatterBoardEntry, BatterInput, SeasonBattingStats
from models.pitcher import PitcherBoardEntry, PitcherInput
from research.prediction_snapshot import (
    build_batter_snapshot,
    build_snapshot,
    list_snapshots,
    load_latest_snapshot,
    load_snapshot,
    save_snapshot,
)
from research.quality_report import build_batter_quality_report, build_quality_report


def _batter_entry(pid, name):
    return BatterBoardEntry(
        player_id=pid, name=name, team="AAA", opponent="BBB", batting_order=3,
        projection=8.0, ceiling=14.0, floor=3.0,
        overall_score=60.0, hitting_skill_score=60.0, power_score=55.0, contact_score=60.0,
        matchup_score=55.0, recent_trend_score=50.0, lineup_position_score=65.0,
        environment_score=50.0, value_score=50.0, risk_score=30.0, confidence=70.0,
        tags=["elite_power"], reasons=["some reason"],
    )


def _batter(pid, name):
    return BatterInput(player_id=pid, name=name, team="AAA", opponent="BBB", game_id=f"g{pid}", venue_name="Test Park",
                        batting_order=3, season=SeasonBattingStats(k_percent=20.0))


def _board_and_batters(n):
    entries = [_batter_entry(str(i), f"Hitter {i}") for i in range(n)]
    batters_by_id = {str(i): _batter(str(i), f"Hitter {i}") for i in range(n)}
    return entries, batters_by_id


# ----------------------------------------------------------------------------
# Batter snapshot structure / immutability / all-hitters-preserved
# ----------------------------------------------------------------------------


def test_build_batter_snapshot_includes_model_version_and_research_version():
    board, batters_by_id = _board_and_batters(2)
    quality_report = build_batter_quality_report(list(batters_by_id.values()))
    snapshot = build_batter_snapshot("2026-08-11", board, batters_by_id, quality_report, {}, generated_at="2026-08-11T21:00:00+00:00")

    assert snapshot["model_version"] == BATTER_MODEL_VERSION
    assert "research_package_version" in snapshot
    assert snapshot["slate_date"] == "2026-08-11"


def test_build_batter_snapshot_preserves_every_hitter_not_just_top_20():
    board, batters_by_id = _board_and_batters(35)  # more than the CLI's Top 20 display
    quality_report = build_batter_quality_report(list(batters_by_id.values()))
    snapshot = build_batter_snapshot("2026-08-11", board, batters_by_id, quality_report, {})

    assert snapshot["hitter_count"] == 35
    assert len(snapshot["hitters"]) == 35


def test_build_batter_snapshot_records_missing_lineup_games():
    board, batters_by_id = _board_and_batters(1)
    quality_report = build_batter_quality_report(list(batters_by_id.values()))
    snapshot = build_batter_snapshot(
        "2026-08-11", board, batters_by_id, quality_report, {}, missing_lineup_game_ids=["999"],
    )
    assert snapshot["missing_lineup_game_ids"] == ["999"]


def test_batter_snapshot_record_has_required_fields():
    board, batters_by_id = _board_and_batters(1)
    quality_report = build_batter_quality_report(list(batters_by_id.values()))
    snapshot = build_batter_snapshot("2026-08-11", board, batters_by_id, quality_report, {})
    record = snapshot["hitters"][0]
    for field in [
        "player_id", "name", "team", "opponent", "game_id", "venue", "batting_order",
        "projection", "ceiling", "floor", "overall_score", "power_score", "matchup_score",
        "risk_score", "confidence", "tags", "reasons",
        "season_metrics", "recent_metrics", "vs_rhp", "vs_lhp", "opposing_pitcher", "trend_metrics", "data_status",
    ]:
        assert field in record, f"missing field: {field}"


def test_batter_snapshot_saved_with_batter_board_prefix_and_never_overwrites(tmp_path):
    board, batters_by_id = _board_and_batters(1)
    quality_report = build_batter_quality_report(list(batters_by_id.values()))
    snapshot = build_batter_snapshot("2026-08-11", board, batters_by_id, quality_report, {}, generated_at="2026-08-11T21:00:00+00:00")

    path = save_snapshot(snapshot, output_root=tmp_path, filename_prefix="batter_board")
    assert path.name == "batter_board_20260811T210000.json"
    assert path.exists()

    with pytest.raises(FileExistsError):
        save_snapshot(snapshot, output_root=tmp_path, filename_prefix="batter_board")


def test_batter_and_pitcher_snapshots_coexist_independently(tmp_path):
    """Same date, same output_root -- batter and pitcher snapshots must
    never collide or overwrite each other (different filename prefixes)."""
    board, batters_by_id = _board_and_batters(1)
    bq = build_batter_quality_report(list(batters_by_id.values()))
    batter_snap = build_batter_snapshot("2026-08-11", board, batters_by_id, bq, {}, generated_at="2026-08-11T21:00:00+00:00")
    save_snapshot(batter_snap, output_root=tmp_path, filename_prefix="batter_board")

    pitcher_entry = PitcherBoardEntry(
        player_id="1", name="P", team="AAA", opponent="BBB",
        projection=20.0, ceiling=28.0, floor=12.0, overall_score=60.0, strikeout_score=60.0,
        run_prevention_score=60.0, matchup_score=60.0, workload_score=60.0, contact_score=60.0,
        environment_score=50.0, value_score=50.0, risk_score=30.0, confidence=70.0,
    )
    pitcher_by_id = {"1": PitcherInput(player_id="1", name="P", team="AAA", opponent="BBB")}
    pq = build_quality_report(list(pitcher_by_id.values()))
    pitcher_snap = build_snapshot("2026-08-11", [pitcher_entry], pitcher_by_id, pq, {}, generated_at="2026-08-11T21:00:00+00:00")
    save_snapshot(pitcher_snap, output_root=tmp_path)  # default prefix "pitcher_board"

    assert len(list_snapshots("2026-08-11", output_root=tmp_path, filename_prefix="batter_board")) == 1
    assert len(list_snapshots("2026-08-11", output_root=tmp_path, filename_prefix="pitcher_board")) == 1

    latest_batter = load_latest_snapshot("2026-08-11", output_root=tmp_path, filename_prefix="batter_board")
    latest_pitcher = load_latest_snapshot("2026-08-11", output_root=tmp_path, filename_prefix="pitcher_board")
    assert "hitters" in latest_batter
    assert "pitchers" in latest_pitcher


# ----------------------------------------------------------------------------
# Timezone metadata
# ----------------------------------------------------------------------------


def test_new_pitcher_snapshot_has_utc_local_and_timezone_fields():
    board, batters_by_id = _board_and_batters(0)  # unused, just need a pitcher board
    pitcher_entry = PitcherBoardEntry(
        player_id="1", name="P", team="AAA", opponent="BBB",
        projection=20.0, ceiling=28.0, floor=12.0, overall_score=60.0, strikeout_score=60.0,
        run_prevention_score=60.0, matchup_score=60.0, workload_score=60.0, contact_score=60.0,
        environment_score=50.0, value_score=50.0, risk_score=30.0, confidence=70.0,
    )
    pitcher_by_id = {"1": PitcherInput(player_id="1", name="P", team="AAA", opponent="BBB")}
    pq = build_quality_report(list(pitcher_by_id.values()))
    snap = build_snapshot("2026-08-11", [pitcher_entry], pitcher_by_id, pq, {}, generated_at="2026-08-11T21:55:00+00:00")

    assert snap["generated_at_utc"] == "2026-08-11T21:55:00+00:00"
    assert snap["generated_at_local"].startswith("2026-08-11T16:55:00")  # CDT = UTC-5 in August
    assert snap["timezone"] == "America/Chicago"
    # Old field preserved for backward compatibility.
    assert snap["generated_at"] == "2026-08-11T21:55:00+00:00"


def test_new_batter_snapshot_has_utc_local_and_timezone_fields():
    board, batters_by_id = _board_and_batters(1)
    bq = build_batter_quality_report(list(batters_by_id.values()))
    snap = build_batter_snapshot("2026-08-11", board, batters_by_id, bq, {}, generated_at="2026-08-11T21:55:00+00:00")

    assert snap["generated_at_utc"] == "2026-08-11T21:55:00+00:00"
    assert snap["generated_at_local"].startswith("2026-08-11T16:55:00")
    assert snap["timezone"] == "America/Chicago"


def test_timezone_handles_winter_cst_offset_correctly():
    board, batters_by_id = _board_and_batters(1)
    bq = build_batter_quality_report(list(batters_by_id.values()))
    snap = build_batter_snapshot("2026-01-15", board, batters_by_id, bq, {}, generated_at="2026-01-15T20:00:00+00:00")
    # CST = UTC-6 in January (no daylight saving).
    assert snap["generated_at_local"].startswith("2026-01-15T14:00:00")
    assert snap["generated_at_local"].endswith("-06:00")


# ----------------------------------------------------------------------------
# Backward compatibility with existing (pre-Milestone-7) pitcher snapshots
# ----------------------------------------------------------------------------


def test_old_style_snapshot_without_timezone_fields_still_loads_and_evaluates(tmp_path):
    """Simulates a snapshot written before this milestone -- no
    generated_at_utc/local/timezone keys at all. Must not crash anything
    that reads snapshots. Historical files are never rewritten."""
    old_style_snapshot = {
        "slate_date": "2026-08-05",
        "generated_at": "2026-08-05T16:00:00+00:00",
        "model_version": "0.6.0",
        "research_package_version": "0.1.0",
        "source_metadata": {},
        "pitcher_count": 1,
        "pitchers": [{
            "player_id": "1", "name": "Old Pitcher", "team": "AAA", "opponent": "BBB", "game_id": "g1",
            "projection": 20.0, "ceiling": 28.0, "floor": 12.0, "overall_score": 60.0,
            "tags": [], "reasons": [],
        }],
        "research_quality_report": {},
    }
    path = tmp_path / "2026-08-05"
    path.mkdir()
    snapshot_file = path / "pitcher_board_20260805T160000.json"
    snapshot_file.write_text(json.dumps(old_style_snapshot), encoding="utf-8")

    loaded = load_snapshot(snapshot_file)
    assert "generated_at_utc" not in loaded  # genuinely old-style, not silently backfilled

    # The evaluator (built in Milestone 6, before this fix) must still work unchanged.
    report = evaluate_pitcher_slate(loaded, [])
    assert report.slate_date == "2026-08-05"
    assert report.model_version == "0.6.0"
