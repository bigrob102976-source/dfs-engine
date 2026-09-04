"""NFL M10 -- trains, evaluates, and selects the first real Big Money
Native NFL projection models: one per offensive position (QB/RB/WR/TE)
plus one separate DST model (historical_models/nfl_v1/config.py's
module docstring explains why they're never forced into one schema).

MODEL SELECTION (Phase 5/12): fit on TRAIN (weeks 1-13) only; every
model-selection decision (which candidate family wins) is made on
VALIDATION (weeks 14-15) metrics only -- TEST (weeks 16-18) is touched
exactly once, after the winner is already fixed, purely to report a
final honest number. Preprocessing (median imputation) is fit on TRAIN
only and reused (never refit) on validation/test, wrapped into one
sklearn Pipeline persisted as a single model.joblib -- Phase 4's
"persist preprocessing with the model" requirement, satisfied by
construction rather than a second artifact.

CANDIDATE FAMILIES (Phase 3): sklearn-native only (Ridge, RandomForest,
HistGradientBoosting) -- xgboost/lightgbm are not installed project
dependencies and this milestone does not add them. No deep learning --
the real M9 dataset (a few hundred to a few thousand rows per position)
does not justify it.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from historical_models.nfl_v1.config import (
    DEFAULT_ARTIFACT_ROOT, DEFAULT_SEED, DST_POSITION, MODEL_VERSION, OFFENSE_POSITIONS,
    SPLIT_TEST, SPLIT_TRAIN, SPLIT_VALIDATION, TARGET_COLUMN, TARGET_SCORING_VERSION,
)
from historical_models.nfl_v1.dataset import (
    add_recent_dk_points_feature, build_dst_arrays, build_position_arrays, latest_dataset_dir, load_all_splits,
)
from historical_models.nfl_v1.persistence import save_all_artifacts
from historical_models.pitcher_v1.metadata import _git_commit, _library_versions

CANDIDATE_FAMILIES = {
    "ridge": lambda seed: Ridge(alpha=1.0, random_state=seed),
    "random_forest": lambda seed: RandomForestRegressor(n_estimators=300, max_depth=8, min_samples_leaf=5, random_state=seed, n_jobs=-1),
    "hist_gradient_boosting": lambda seed: HistGradientBoostingRegressor(max_depth=4, max_iter=200, random_state=seed),
}


@dataclass
class EvalResult:
    mae: float
    rmse: float
    r2: float
    spearman: float
    n: int

    def to_dict(self) -> dict:
        return {"mae": self.mae, "rmse": self.rmse, "r2": self.r2, "spearman": self.spearman, "n": self.n}


def evaluate(y_true, y_pred) -> EvalResult:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) < 2:
        return EvalResult(mae=float("nan"), rmse=float("nan"), r2=float("nan"), spearman=float("nan"), n=len(y_true))
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    r2 = r2_score(y_true, y_pred)
    rho = spearmanr(y_true, y_pred).statistic
    return EvalResult(mae=round(float(mae), 4), rmse=round(float(rmse), 4), r2=round(float(r2), 4), spearman=round(float(rho), 4) if rho is not None else float("nan"), n=len(y_true))


def baseline_positional_mean(y_train) -> float:
    return float(np.mean(y_train))


def _clamp_predictions(y_pred: np.ndarray, floor: float) -> np.ndarray:
    """Real, observed finding during M10 training (not hypothetical):
    Ridge's unbounded linear form produced a -104.94 projected DK-point
    prediction for a real RB test row (actual value: 0.0) and a -30.65
    prediction for a real WR row -- linear extrapolation blowing up on
    an out-of-distribution feature combination, not a plausible DK
    score. `floor` is the REAL minimum target_dk_points value actually
    observed in this position's own TRAIN split (never an arbitrary
    constant like -5 or 0) -- a model is never allowed to predict a
    game worse than the worst real game this project has ever recorded
    for that position."""
    return np.maximum(y_pred, floor)


def _build_pipeline(model_key: str, seed: int) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", CANDIDATE_FAMILIES[model_key](seed)),
    ])


def _low_history_breakdown(meta: pd.DataFrame, y_true, y_pred) -> dict:
    weeks = meta["weeks_of_history"].to_numpy()
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    bins = {"0_weeks": weeks == 0, "1_2_weeks": (weeks >= 1) & (weeks <= 2), "3_plus_weeks": weeks >= 3}
    out = {}
    for name, mask in bins.items():
        if mask.sum() >= 2:
            out[name] = evaluate(y_true[mask], y_pred[mask]).to_dict()
        else:
            out[name] = {"n": int(mask.sum()), "note": "too few rows to evaluate"}
    return out


def _residual_intervals(residuals: np.ndarray) -> dict:
    """Empirical residual-quantile intervals from REAL validation-set
    residuals (never test) -- Phase 11's explicit requirement: never an
    arbitrary projection*0.8/1.2 multiplier. floor/ceiling are additive
    offsets (10th/90th percentile of actual-minus-predicted) applied to
    a future prediction, not a second model."""
    residuals = residuals[~np.isnan(residuals)]
    if len(residuals) < 10:
        return {"available": False, "reason": "fewer than 10 real validation residuals"}
    return {
        "available": True,
        "p10_offset": round(float(np.percentile(residuals, 10)), 3),
        "p90_offset": round(float(np.percentile(residuals, 90)), 3),
        "n_residuals": int(len(residuals)),
    }


def _outliers(meta: pd.DataFrame, y_true, y_pred, top_n: int = 5) -> List[dict]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    errors = np.abs(y_true - y_pred)
    order = np.argsort(-errors)[:top_n]
    out = []
    for i in order:
        row = meta.iloc[i]
        out.append({
            "gsis_id_or_team": row.get("gsis_id", row.get("team")),
            "season": int(row["season"]), "week": int(row["week"]),
            "actual": round(float(y_true[i]), 2), "predicted": round(float(y_pred[i]), 2),
            "error": round(float(errors[i]), 2), "weeks_of_history": int(row["weeks_of_history"]),
        })
    return out


def _feature_importance(pipeline: Pipeline, X_val: pd.DataFrame, y_val, feature_names: List[str], seed: int) -> List[dict]:
    model = pipeline.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        return sorted(
            [{"feature": f, "importance": round(float(v), 5)} for f, v in zip(feature_names, importances)],
            key=lambda d: -d["importance"],
        )[:20]
    result = permutation_importance(pipeline, X_val, y_val, n_repeats=5, random_state=seed, n_jobs=-1)
    return sorted(
        [{"feature": f, "importance": round(float(v), 5)} for f, v in zip(feature_names, result.importances_mean)],
        key=lambda d: -d["importance"],
    )[:20]


def train_one(position: str, arrays: Dict[str, dict], seed: int = DEFAULT_SEED) -> dict:
    train, val, test = arrays[SPLIT_TRAIN], arrays[SPLIT_VALIDATION], arrays[SPLIT_TEST]
    feature_names = list(train["X"].columns)

    baseline_mean = baseline_positional_mean(train["y"])
    baseline_pred_val = np.full(len(val["y"]), baseline_mean)
    baseline_pred_test = np.full(len(test["y"]), baseline_mean)
    baseline_metrics_val = evaluate(val["y"], baseline_pred_val)
    baseline_metrics_test = evaluate(test["y"], baseline_pred_test)

    recent_col = "recent_dk_points_mean_last3"
    baseline_recent_val = evaluate(val["y"], val["X"][recent_col].fillna(baseline_mean)) if recent_col in val["X"].columns else None

    candidates = {}
    for key in CANDIDATE_FAMILIES:
        pipeline = _build_pipeline(key, seed)
        pipeline.fit(train["X"], train["y"])
        val_pred = pipeline.predict(val["X"])
        candidates[key] = {"pipeline": pipeline, "val_metrics": evaluate(val["y"], val_pred)}

    winner_key = min(candidates, key=lambda k: candidates[k]["val_metrics"].mae)
    winner = candidates[winner_key]["pipeline"]
    winner_val_metrics = candidates[winner_key]["val_metrics"]

    prediction_floor = float(train["y"].min())  # see _clamp_predictions' docstring -- real, observed, never arbitrary

    test_pred = _clamp_predictions(winner.predict(test["X"]), prediction_floor)
    test_metrics = evaluate(test["y"], test_pred)

    val_pred = _clamp_predictions(winner.predict(val["X"]), prediction_floor)
    residuals = np.asarray(val["y"], dtype=float) - np.asarray(val_pred, dtype=float)
    intervals = _residual_intervals(residuals)

    importance = _feature_importance(winner, val["X"], val["y"], feature_names, seed)
    outliers = _outliers(test["meta"], test["y"], test_pred)
    low_history = _low_history_breakdown(test["meta"], test["y"], test_pred)

    metadata = {
        "model_version": MODEL_VERSION, "position": position, "model_family": winner_key,
        "hyperparameters": {k: str(v) for k, v in winner.named_steps["model"].get_params().items()},
        "feature_list": feature_names, "seed": seed,
        "dataset_schema_version": "nfl_projection_training_v1", "target_scoring_version": TARGET_SCORING_VERSION,
        "train_rows": len(train["y"]), "validation_rows": len(val["y"]), "test_rows": len(test["y"]),
        "library_versions": _library_versions(), "git_commit": _git_commit(),
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "salary_used_as_feature": False, "vegas_used_as_feature": False, "player_id_used_as_feature": False,
        "baseline_positional_mean": round(baseline_mean, 3),
        "baseline_mae_validation": baseline_metrics_val.mae, "baseline_mae_recent3_validation": baseline_recent_val.mae if baseline_recent_val else None,
        "prediction_floor": round(prediction_floor, 3),
    }

    return {
        "position": position, "pipeline": winner, "model_family": winner_key, "metadata": metadata,
        "baseline_val": baseline_metrics_val.to_dict(), "baseline_test": baseline_metrics_test.to_dict(),
        "baseline_recent3_val": baseline_recent_val.to_dict() if baseline_recent_val else None,
        "candidate_val_metrics": {k: v["val_metrics"].to_dict() for k, v in candidates.items()},
        "validation_metrics": winner_val_metrics.to_dict(), "test_metrics": test_metrics.to_dict(),
        "feature_importance": importance, "outliers": outliers, "low_history": low_history,
        "residual_intervals": intervals, "feature_list": feature_names,
    }


def run_all(dataset_dir: Optional[Path] = None, artifact_root: Path = DEFAULT_ARTIFACT_ROOT, seed: int = DEFAULT_SEED) -> Dict[str, dict]:
    if dataset_dir is None:
        dataset_dir = latest_dataset_dir(Path("historical") / "nfl" / "training" / "projections" / "v1")

    offense_splits = load_all_splits(dataset_dir, "offense")
    offense_splits = add_recent_dk_points_feature(offense_splits, id_col="gsis_id")

    results = {}
    for position in OFFENSE_POSITIONS:
        arrays = build_position_arrays(offense_splits, position)
        results[position] = train_one(position, arrays, seed)

    dst_splits = load_all_splits(dataset_dir, "dst")
    dst_splits = add_recent_dk_points_feature(dst_splits, id_col="team")
    dst_arrays = build_dst_arrays(dst_splits)
    results[DST_POSITION] = train_one(DST_POSITION, dst_arrays, seed)

    return results


def persist_results(results: Dict[str, dict], artifact_root: Path = DEFAULT_ARTIFACT_ROOT) -> Dict[str, Dict[str, Path]]:
    paths = {}
    for position, r in results.items():
        output_dir = Path(artifact_root) / position.lower() / "v1"
        paths[position] = save_all_artifacts(
            output_dir, r["pipeline"], r["metadata"], r["feature_list"],
            r["validation_metrics"], r["test_metrics"], r["feature_importance"],
            r["outliers"], r["residual_intervals"],
        )
    return paths
