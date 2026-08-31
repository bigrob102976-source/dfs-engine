"""NFL M6C -- targeted tests for historical_nfl/usage_quality.py."""

from historical_nfl.usage_models import NflUsageRecord
from historical_nfl.usage_quality import build_usage_quality_report

SEASON, WEEK = 2025, 1


def _record(gsis_id, position="WR", canonical=None, snap_share=None, target_share=None, carry_share=None):
    return NflUsageRecord(
        canonical_player_id=canonical, gsis_id=gsis_id, season=SEASON, week=WEEK, game_id="g1",
        team="PHI", opponent="DAL", position=position, snap_share=snap_share, target_share=target_share, carry_share=carry_share,
    )


def test_basic_counts():
    records = [_record("00-1", canonical="gsis:00-1"), _record("00-2", canonical=None)]
    report = build_usage_quality_report(records, SEASON, WEEK, snap_rows=10, participation_rows=5, unresolved_gsis_ids=["00-2"])
    assert report.usage_rows == 2
    assert report.gsis_ids_present == 2
    assert report.canonical_matches == 1
    assert report.unmapped_gsis_rows == 1
    assert report.snap_rows == 10
    assert report.participation_rows == 5


def test_by_position_breakdown():
    records = [_record("00-1", position="QB", canonical="gsis:00-1"), _record("00-2", position="QB", canonical=None), _record("00-3", position="RB", canonical="gsis:00-3")]
    report = build_usage_quality_report(records, SEASON, WEEK, 0, 0, [])
    assert report.by_position["QB"] == {"total": 2, "canonical_matches": 1}
    assert report.by_position["RB"] == {"total": 1, "canonical_matches": 1}
    assert report.by_position["WR"] == {"total": 0, "canonical_matches": 0}


def test_coverage_percent():
    records = [_record("00-1", snap_share=0.5, target_share=0.3), _record("00-2", snap_share=None, target_share=None)]
    report = build_usage_quality_report(records, SEASON, WEEK, 0, 0, [])
    assert report.coverage_percent["snap_share"] == 50.0
    assert report.coverage_percent["target_share"] == 50.0
    assert report.coverage_percent["routes"] == 0.0  # never populated in M6C


def test_duplicate_key_detection():
    records = [_record("00-1"), _record("00-1")]
    report = build_usage_quality_report(records, SEASON, WEEK, 0, 0, [])
    assert report.duplicate_keys == 2


def test_no_duplicates_for_distinct_players():
    records = [_record("00-1"), _record("00-2")]
    report = build_usage_quality_report(records, SEASON, WEEK, 0, 0, [])
    assert report.duplicate_keys == 0


def test_invalid_range_detection_never_silently_clamps():
    records = [_record("00-1", snap_share=1.5), _record("00-2", target_share=-0.1), _record("00-3", carry_share=0.5)]
    report = build_usage_quality_report(records, SEASON, WEEK, 0, 0, [])
    assert report.invalid_range_values == 2  # the 1.5 and the -0.1 -- never clamped, never dropped
    assert records[0].snap_share == 1.5  # unmodified


def test_empty_records_never_crashes():
    report = build_usage_quality_report([], SEASON, WEEK, 0, 0, [])
    assert report.usage_rows == 0
    assert report.coverage_percent["snap_share"] == 0.0
