"""NFL M10 -- targeted tests for historical_models/nfl_v1/train.py."""

import numpy as np
import pandas as pd

from historical_models.nfl_v1.train import _clamp_predictions, _low_history_breakdown, _residual_intervals, evaluate


def test_evaluate_returns_real_metrics():
    y_true = [10.0, 20.0, 30.0, 40.0]
    y_pred = [12.0, 18.0, 33.0, 38.0]
    result = evaluate(y_true, y_pred)
    assert result.n == 4
    assert result.mae > 0
    assert result.rmse >= result.mae  # RMSE never smaller than MAE


def test_evaluate_handles_nan_gracefully():
    y_true = [10.0, np.nan, 30.0]
    y_pred = [12.0, 18.0, 33.0]
    result = evaluate(y_true, y_pred)
    assert result.n == 2  # the NaN row excluded, never fabricated


def test_clamp_predictions_bounds_at_real_observed_floor():
    """The core M10 fix: a real Ridge extrapolation blowup (-104.94 for
    a real actual value of 0.0) must never reach a caller unclamped."""
    preds = np.array([-104.94, 5.0, -1.0, 30.0])
    floor = -3.0  # the real minimum observed in some position's TRAIN split
    clamped = _clamp_predictions(preds, floor)
    assert clamped[0] == -3.0
    assert clamped[1] == 5.0  # untouched -- well within range
    assert clamped[2] == -1.0  # untouched -- above the floor already
    assert clamped[3] == 30.0


def test_residual_intervals_none_available_with_too_few_residuals():
    result = _residual_intervals(np.array([1.0, 2.0, 3.0]))
    assert result["available"] is False


def test_residual_intervals_real_percentiles():
    residuals = np.array(list(range(-10, 10)), dtype=float)  # -10..9
    result = _residual_intervals(residuals)
    assert result["available"] is True
    assert result["p10_offset"] < 0
    assert result["p90_offset"] > 0
    assert result["n_residuals"] == 20


def test_low_history_breakdown_segments_correctly():
    meta = pd.DataFrame({"weeks_of_history": [0, 0, 1, 2, 5, 8]})
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    y_pred = np.array([1.5, 2.5, 3.5, 4.5, 5.5, 6.5])
    result = _low_history_breakdown(meta, y_true, y_pred)
    assert result["0_weeks"]["n"] == 2
    assert result["1_2_weeks"]["n"] == 2
    assert result["3_plus_weeks"]["n"] == 2


def test_low_history_breakdown_too_few_rows_reports_note_not_a_fake_metric():
    meta = pd.DataFrame({"weeks_of_history": [0]})
    y_true = np.array([1.0])
    y_pred = np.array([1.5])
    result = _low_history_breakdown(meta, y_true, y_pred)
    assert "note" in result["0_weeks"]
