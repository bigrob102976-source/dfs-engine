import pytest

from evaluation.ownership_evaluator import evaluate_ownership
from tests._ownership_evaluation_fixtures import sample_actual_document, sample_snapshot


def _report():
    return evaluate_ownership(sample_snapshot(), sample_actual_document())


def test_matched_counts_and_rate():
    report = _report()
    assert report.matched_count == 8
    assert report.actual_record_count == 8
    assert report.match_rate == 1.0
    assert report.unmatched_count == 0
    assert report.ambiguous_count == 0


def test_hitter_mae_rmse_bias_hand_computed():
    report = _report()
    hm = report.hitter_metrics
    assert hm["count"] == 6
    assert hm["mae"] == pytest.approx(6.5, abs=0.001)
    assert hm["rmse"] == pytest.approx((303 / 6) ** 0.5, abs=0.001)
    assert hm["bias"] == pytest.approx(5 / 6, abs=0.001)
    assert hm["median_abs_error"] == pytest.approx(6.0, abs=0.001)
    assert hm["max_abs_error"] == pytest.approx(10.0, abs=0.001)


def test_pitcher_mae_and_bias_hand_computed():
    report = _report()
    pm = report.pitcher_metrics
    assert pm["count"] == 2
    assert pm["mae"] == pytest.approx(10.0, abs=0.001)
    assert pm["bias"] == pytest.approx(0.0, abs=0.001)
    assert pm["correlation"] == pytest.approx(1.0, abs=0.001)


def test_overall_mae_combines_pitchers_and_hitters():
    report = _report()
    om = report.overall_metrics
    assert om["count"] == 8
    assert om["mae"] == pytest.approx(59 / 8, abs=0.001)
    assert om["bias"] == pytest.approx(5 / 8, abs=0.001)


def test_correlation_within_valid_range():
    report = _report()
    for metrics in (report.overall_metrics, report.pitcher_metrics, report.hitter_metrics):
        if metrics["correlation"] is not None:
            assert -1.0 <= metrics["correlation"] <= 1.0


def test_hitter_rank_correlation_hand_computed():
    report = _report()
    assert report.hitter_metrics["rank_correlation"] == pytest.approx(0.9429, abs=0.01)


def test_pitcher_rank_error_is_zero_when_order_matches():
    report = _report()
    p_records = [r for r in report.records if r["player_type"] == "pitcher"]
    assert all(r["rank_error"] == 0 for r in p_records)


def test_ownership_ranks_assigned_within_player_type():
    report = _report()
    by_id = {r["dk_player_id"]: r for r in report.records}
    assert by_id["p1"]["projected_rank"] == 1  # best pitcher by projection
    assert by_id["h1"]["projected_rank"] == 1  # best hitter by projection (independent ranking space)


def test_ownership_tier_actual_recomputed_from_actual_value():
    report = _report()
    by_id = {r["dk_player_id"]: r for r in report.records}
    # h4: projected 20 (tier "high"), actual 30 -> actual tier should be "very_high"
    assert by_id["h4"]["ownership_tier_projected"] == "high"
    assert by_id["h4"]["ownership_tier_actual"] == "very_high"


def test_tier_summary_very_high_group_hand_computed():
    report = _report()
    very_high = [t for t in report.tier_summary if t["tier"] == "very_high"][0]
    assert very_high["count"] == 4
    assert very_high["avg_projected_ownership"] == pytest.approx(60.0, abs=0.01)
    assert very_high["avg_actual_ownership"] == pytest.approx(55.0, abs=0.01)
    assert very_high["mae"] == pytest.approx(7.5, abs=0.01)


def test_tier_confusion_tracks_projected_to_actual_moves():
    report = _report()
    # h4 moved from projected "high" to actual "very_high".
    assert report.tier_confusion["high"]["very_high"] == 1


def test_chalk_precision_and_recall_hand_computed():
    report = _report()
    ce = report.chalk_evaluation
    assert ce["predicted_chalk_count"] == 5
    assert ce["actual_chalk_count"] == 6
    assert ce["precision"] == pytest.approx(1.0, abs=0.001)
    assert ce["recall"] == pytest.approx(5 / 6, abs=0.001)


def test_top5_hit_rate_hand_computed():
    report = _report()
    assert report.top5_hit_rate == pytest.approx(1.0, abs=0.001)


def test_top10_hit_rate_none_when_fewer_than_10_matched():
    report = _report()
    assert report.top10_hit_rate is None


def test_biggest_under_projections_sorted_by_positive_error():
    report = _report()
    under = report.biggest_under_projections
    # p2 and h4 are tied for the largest positive error (+10).
    assert under[0]["dk_player_id"] in ("p2", "h4")
    assert under[0]["error"] == 10
    assert all(under[i]["error"] >= under[i + 1]["error"] for i in range(len(under) - 1))


def test_biggest_over_projections_sorted_by_negative_error():
    report = _report()
    over = report.biggest_over_projections
    assert over[0]["dk_player_id"] in ("p1", "h1")  # both -10, most negative
    assert over[0]["error"] == -10


def test_team_popularity_evaluation_hand_computed():
    report = _report()
    by_team = {t["team"]: t for t in report.team_popularity_evaluation}
    assert by_team["PHI"]["actual_aggregate_player_ownership"] == pytest.approx(135.0, abs=0.01)
    assert by_team["NYY"]["actual_aggregate_player_ownership"] == pytest.approx(65.0, abs=0.01)
    assert by_team["BAL"]["actual_aggregate_player_ownership"] == pytest.approx(20.0, abs=0.01)
    assert by_team["PHI"]["projected_rank"] == 1
    assert by_team["PHI"]["actual_rank"] == 1
    assert by_team["PHI"]["rank_error"] == 0


def test_team_rank_error_detects_a_swap():
    from evaluation.ownership_evaluator import evaluate_ownership
    snap = sample_snapshot()
    doc = sample_actual_document()
    # Swap NYY and BAL's actual ownership so the ranking flips.
    for r in doc["records"]:
        if r["dk_player_id"] == "h5":
            r["actual_ownership"] = 90.0  # BAL's SS suddenly super high-owned
    report = evaluate_ownership(snap, doc)
    by_team = {t["team"]: t for t in report.team_popularity_evaluation}
    # BAL (was last) now clearly outranks NYY -- confirms rank_error reacts to real changes.
    assert by_team["BAL"]["actual_rank"] < by_team["NYY"]["actual_rank"]
    assert by_team["BAL"]["rank_error"] != 0


def test_tag_performance_includes_configured_tags():
    report = _report()
    tags = {t["tag"] for t in report.tag_performance}
    assert "elite_leverage" in tags
    assert "chalk" in tags
    elite = [t for t in report.tag_performance if t["tag"] == "elite_leverage"][0]
    assert elite["count"] == 1
    assert elite["avg_projected_ownership"] == pytest.approx(60.0, abs=0.01)
    assert elite["avg_actual_ownership"] == pytest.approx(50.0, abs=0.01)


def test_position_evaluation_counts_multi_position_hitter_in_both_positions():
    report = _report()
    by_pos = {p["position"]: p for p in report.position_evaluation}
    # h4 is eligible at 3B and OF -- must appear in both groups (documented, not silently dropped).
    assert any(r["dk_player_id"] == "h4" for r in [rec for rec in report.records if "3B" in rec["dk_positions"]])
    assert by_pos["3B"]["count"] == 1
    assert by_pos["OF"]["count"] == 2  # h4 and h6


def test_salary_band_evaluation_groups_correctly():
    report = _report()
    bands = {b["band"]: b for b in report.hitter_salary_band_evaluation}
    # h6=2000, h1=2500 -> "<$3K"; h2=3200, h5=3600 -> "$3K-$4K"
    assert bands["<$3K"]["count"] == 2
    assert bands["$3K-$4K"]["count"] == 2


def test_unmatched_actual_record_not_counted_in_metrics():
    snap = sample_snapshot()
    doc = sample_actual_document()
    doc["records"].append({
        "dk_player_id": None, "mlb_player_id": None, "name": "Nobody", "team": None, "player_type": None,
        "actual_ownership": 5.0, "contest_id": "999", "contest_name": None, "contest_size": 8,
        "source_file": "x.csv", "match_status": "unmatched", "match_confidence": None,
    })
    doc["record_count"] += 1
    doc["unmatched_count"] += 1
    report = evaluate_ownership(snap, doc)
    assert report.matched_count == 8  # unchanged
    assert report.unmatched_count == 1


def test_deterministic_repeated_evaluation():
    first = evaluate_ownership(sample_snapshot(), sample_actual_document())
    second = evaluate_ownership(sample_snapshot(), sample_actual_document())
    assert first.overall_metrics == second.overall_metrics
    assert [r["dk_player_id"] for r in first.records] == [r["dk_player_id"] for r in second.records]


def test_evaluator_version_and_model_version_recorded():
    from config.ownership_evaluation_config import OWNERSHIP_EVALUATOR_VERSION
    report = _report()
    assert report.evaluator_version == OWNERSHIP_EVALUATOR_VERSION
    assert report.ownership_model_version == "0.1.0"
