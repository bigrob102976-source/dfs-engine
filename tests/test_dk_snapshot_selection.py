from config.batter_scoring_config import BATTER_MODEL_VERSION
from dfs.snapshot_selection import select_snapshot
from models.batter import BatterBoardEntry, BatterInput, SeasonBattingStats
from research.prediction_snapshot import build_batter_snapshot, save_snapshot
from research.quality_report import build_batter_quality_report


def _make_and_save_snapshot(tmp_path, generated_at):
    entry = BatterBoardEntry(
        player_id="1", name="H", team="AAA", opponent="BBB", batting_order=3,
        projection=8.0, ceiling=14.0, floor=3.0, overall_score=60.0, hitting_skill_score=60.0,
        power_score=55.0, contact_score=60.0, matchup_score=55.0, recent_trend_score=50.0,
        lineup_position_score=65.0, environment_score=50.0, value_score=50.0, risk_score=30.0, confidence=70.0,
    )
    batter = BatterInput(player_id="1", name="H", team="AAA", opponent="BBB", game_id="g1", batting_order=3,
                          season=SeasonBattingStats(k_percent=20.0))
    quality_report = build_batter_quality_report([batter])
    snapshot = build_batter_snapshot("2026-08-11", [entry], {"1": batter}, quality_report, {}, generated_at=generated_at)
    return save_snapshot(snapshot, output_root=tmp_path, filename_prefix="batter_board")


def test_selects_latest_when_no_explicit_path_given(tmp_path):
    _make_and_save_snapshot(tmp_path, "2026-08-11T14:00:00+00:00")
    later_path = _make_and_save_snapshot(tmp_path, "2026-08-11T20:00:00+00:00")

    snapshot, path = select_snapshot(None, "2026-08-11", tmp_path, "batter_board")
    assert path == str(later_path)
    assert snapshot["generated_at_utc"] == "2026-08-11T20:00:00+00:00"


def test_selects_explicit_path_even_if_not_latest(tmp_path):
    earlier_path = _make_and_save_snapshot(tmp_path, "2026-08-11T14:00:00+00:00")
    _make_and_save_snapshot(tmp_path, "2026-08-11T20:00:00+00:00")

    snapshot, path = select_snapshot(str(earlier_path), "2026-08-11", tmp_path, "batter_board")
    assert path == str(earlier_path)
    assert snapshot["generated_at_utc"] == "2026-08-11T14:00:00+00:00"


def test_returns_none_gracefully_when_no_snapshot_exists(tmp_path):
    snapshot, path = select_snapshot(None, "2026-08-11", tmp_path, "batter_board")
    assert snapshot is None
    assert path is None


def test_model_version_preserved_through_selection(tmp_path):
    _make_and_save_snapshot(tmp_path, "2026-08-11T14:00:00+00:00")
    snapshot, _ = select_snapshot(None, "2026-08-11", tmp_path, "batter_board")
    assert snapshot["model_version"] == BATTER_MODEL_VERSION
