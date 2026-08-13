import pytest

from evaluation.pitcher_evaluator import evaluate_slate


def _pred(pid, name, projection, ceiling=None, floor=None, overall_score=None, risk_score=30.0, confidence=60.0, tags=None):
    return {
        "player_id": pid, "name": name, "team": "AAA", "opponent": "BBB", "game_id": f"g{pid}",
        "projection": projection,
        "ceiling": ceiling if ceiling is not None else projection + 10,
        "floor": floor if floor is not None else max(projection - 10, 0),
        "overall_score": overall_score if overall_score is not None else projection * 2,
        "risk_score": risk_score, "confidence": confidence, "tags": tags or [],
    }


def _actual(pid, status="completed_start", dfs_points=None):
    return {"player_id": pid, "game_id": f"g{pid}", "status": status, "dfs_points": dfs_points}


def _snapshot(predictions):
    return {"slate_date": "2026-08-05", "generated_at": "2026-08-05T16:00:00+00:00", "model_version": "0.6.0", "pitchers": predictions}


# ----------------------------------------------------------------------------
# Core error metrics
# ----------------------------------------------------------------------------


def test_projection_error_and_abs_error_signs():
    snapshot = _snapshot([_pred("1", "A", 20.0)])
    results = [_actual("1", dfs_points=25.0)]  # overperformed by 5
    report = evaluate_slate(snapshot, results)
    record = report.records[0]
    assert record["error"] == 5.0
    assert record["abs_error"] == 5.0
    assert record["squared_error"] == 25.0


def test_mae_and_rmse():
    snapshot = _snapshot([_pred("1", "A", 20.0), _pred("2", "B", 10.0)])
    results = [_actual("1", dfs_points=25.0), _actual("2", dfs_points=5.0)]  # errors: +5, -5
    report = evaluate_slate(snapshot, results)
    assert report.slate_metrics["mae"] == 5.0
    assert report.slate_metrics["rmse"] == 5.0


def test_ceiling_hit_and_floor_miss():
    snapshot = _snapshot([_pred("1", "A", 20.0, ceiling=30.0, floor=10.0), _pred("2", "B", 20.0, ceiling=30.0, floor=10.0)])
    results = [_actual("1", dfs_points=35.0), _actual("2", dfs_points=5.0)]  # exceeds ceiling / below floor
    report = evaluate_slate(snapshot, results)
    by_id = {r["player_id"]: r for r in report.records}
    assert by_id["1"]["ceiling_hit"] is True
    assert by_id["1"]["floor_miss"] is False
    assert by_id["2"]["ceiling_hit"] is False
    assert by_id["2"]["floor_miss"] is True
    assert report.slate_metrics["ceiling_hit_rate"] == 0.5
    assert report.slate_metrics["floor_miss_rate"] == 0.5


# ----------------------------------------------------------------------------
# Ranking
# ----------------------------------------------------------------------------


def test_rank_calculation_and_rank_error_sign_matches_milestone_example():
    # Pitcher A: pred rank 1, actual rank 2 -> difference +1
    # Pitcher B: pred rank 2, actual rank 1 -> difference -1
    snapshot = _snapshot([_pred("A", "A", 30.0), _pred("B", "B", 20.0)])
    results = [_actual("A", dfs_points=20.0), _actual("B", dfs_points=25.0)]
    report = evaluate_slate(snapshot, results)
    by_id = {r["player_id"]: r for r in report.records}
    assert by_id["A"]["predicted_rank"] == 1
    assert by_id["A"]["actual_rank"] == 2
    assert by_id["A"]["rank_error"] == 1
    assert by_id["B"]["predicted_rank"] == 2
    assert by_id["B"]["actual_rank"] == 1
    assert by_id["B"]["rank_error"] == -1


def test_top5_hit_rate_perfect_and_none():
    preds = [_pred(str(i), f"P{i}", 30.0 - i) for i in range(6)]  # ranked 0..5 by projection descending
    results = [_actual(str(i), dfs_points=30.0 - i) for i in range(6)]  # same order -> perfect hit rate
    report = evaluate_slate(_snapshot(preds), results)
    assert report.top5_hit_rate == 1.0


def test_top5_hit_rate_none_when_fewer_than_5_eligible():
    preds = [_pred(str(i), f"P{i}", 20.0) for i in range(3)]
    results = [_actual(str(i), dfs_points=20.0) for i in range(3)]
    report = evaluate_slate(_snapshot(preds), results)
    assert report.top5_hit_rate is None


# ----------------------------------------------------------------------------
# Status handling / eligibility
# ----------------------------------------------------------------------------


def test_missing_actual_result_handled_as_missing_result_status():
    snapshot = _snapshot([_pred("1", "A", 20.0)])
    report = evaluate_slate(snapshot, [])  # no matching actual result at all
    assert report.records[0]["status"] == "missing_result"
    assert report.records[0]["eligible"] is False
    assert report.slate_metrics["pitchers_evaluated"] == 0


def test_only_completed_start_counts_toward_accuracy_metrics():
    snapshot = _snapshot([_pred("1", "A", 20.0), _pred("2", "B", 20.0), _pred("3", "C", 20.0)])
    results = [
        _actual("1", status="completed_start", dfs_points=25.0),
        _actual("2", status="scratched", dfs_points=None),
        _actual("3", status="postponed", dfs_points=None),
    ]
    report = evaluate_slate(snapshot, results)
    assert report.status_breakdown == {"completed_start": 1, "scratched": 1, "postponed": 1}
    assert report.slate_metrics["pitchers_evaluated"] == 1
    assert report.pitcher_count_predicted == 3


def test_pitcher_who_never_started_excluded_from_metrics_but_preserved():
    snapshot = _snapshot([_pred("1", "A", 20.0)])
    results = [_actual("1", status="did_not_start", dfs_points=8.0)]
    report = evaluate_slate(snapshot, results)
    record = report.records[0]
    assert record["status"] == "did_not_start"
    assert record["eligible"] is False
    assert report.slate_metrics["pitchers_evaluated"] == 0


# ----------------------------------------------------------------------------
# Tag / bucket aggregation
# ----------------------------------------------------------------------------


def test_tag_performance_aggregation():
    snapshot = _snapshot([
        _pred("1", "A", 20.0, tags=["elite_csw"]),
        _pred("2", "B", 20.0, tags=["elite_csw"]),
        _pred("3", "C", 20.0, tags=[]),
    ])
    results = [
        _actual("1", dfs_points=25.0),
        _actual("2", dfs_points=15.0),
        _actual("3", dfs_points=20.0),
    ]
    report = evaluate_slate(snapshot, results)
    tag_perf = {t["tag"]: t for t in report.tag_performance}
    assert tag_perf["elite_csw"]["count"] == 2
    assert tag_perf["elite_csw"]["avg_actual_dfs_points"] == 20.0  # (25+15)/2
    assert "elite_csw" in tag_perf and len(tag_perf) == 1  # untagged pitcher contributes no tag row


def test_confidence_bucket_aggregation():
    snapshot = _snapshot([
        _pred("1", "A", 20.0, confidence=35.0),   # bucket 0-39
        _pred("2", "B", 20.0, confidence=85.0),   # bucket 80+
    ])
    results = [_actual("1", dfs_points=25.0), _actual("2", dfs_points=21.0)]
    report = evaluate_slate(snapshot, results)
    buckets = {b["bucket"]: b for b in report.confidence_bucket_summary}
    assert buckets["0-39"]["count"] == 1
    assert buckets["0-39"]["mae"] == 5.0
    assert buckets["80+"]["count"] == 1
    assert buckets["80+"]["mae"] == 1.0
    assert buckets["40-49"]["count"] == 0


def test_risk_bucket_aggregation():
    snapshot = _snapshot([
        _pred("1", "A", 20.0, risk_score=20.0),   # low
        _pred("2", "B", 20.0, risk_score=55.0),   # high
    ])
    results = [_actual("1", dfs_points=20.0), _actual("2", dfs_points=5.0)]  # #2 misses floor
    report = evaluate_slate(snapshot, results)
    buckets = {b["bucket"]: b for b in report.risk_bucket_summary}
    assert buckets["low"]["count"] == 1
    assert buckets["high"]["count"] == 1
    assert buckets["high"]["bust_rate"] == 1.0
    assert buckets["low"]["bust_rate"] == 0.0


# ----------------------------------------------------------------------------
# Best/worst calls, surprises/busts
# ----------------------------------------------------------------------------


def test_best_and_worst_calls_ranked_by_absolute_rank_error():
    preds = [_pred(str(i), f"P{i}", 30.0 - i) for i in range(4)]  # pred ranks 1..4
    # actuals reversed relative to prediction for player "3" (biggest rank error)
    results = [
        _actual("0", dfs_points=27.0),  # pred1 act1 -> err 0
        _actual("1", dfs_points=26.0),  # pred2 act2 -> err 0
        _actual("2", dfs_points=25.0),  # pred3 act3 -> err 0
        _actual("3", dfs_points=100.0),  # pred4 act1 -> err -3 (huge positive surprise + rank swing)
    ]
    report = evaluate_slate(_snapshot(preds), results)
    worst_ids = {r["player_id"] for r in report.worst_calls}
    assert "3" in worst_ids


def test_biggest_positive_surprise_and_bust():
    snapshot = _snapshot([_pred("1", "A", 10.0), _pred("2", "B", 10.0)])
    results = [_actual("1", dfs_points=30.0), _actual("2", dfs_points=0.0)]
    report = evaluate_slate(snapshot, results)
    assert report.biggest_positive_surprises[0]["player_id"] == "1"
    assert report.biggest_busts[0]["player_id"] == "2"
