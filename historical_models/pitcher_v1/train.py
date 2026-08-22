"""Milestone 32.2 -- training pipeline entry point.

    python -m historical_models.pitcher_v1.train [--warehouse-path P] [--output-dir D] [--seed N]

Workflow (Part "FINAL TEST DISCIPLINE"): train every candidate x
hyperparameter combination, score each ONCE on VALIDATION, select the
single best by validation MAE, FREEZE it, then evaluate that frozen
pipeline exactly ONCE on the untouched TEST set. Nothing after the test
evaluation feeds back into model/feature selection.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from historical_models.pitcher_v1.config import DEFAULT_ARTIFACT_DIR, DEFAULT_SEED, DEFAULT_WAREHOUSE_PITCHER_PARQUET, TARGET_COLUMN
from historical_models.pitcher_v1.dataset import (
    build_dataset_summary, chronological_split, load_starting_pitcher_dataset, missingness_by_family,
)
from historical_models.pitcher_v1.evaluate import (
    compute_bucket_analysis, compute_calibration_table, compute_outliers, compute_permutation_importance,
    compute_primary_metrics, compute_top_decile_actual_avg, compute_topn_metrics,
)
from historical_models.pitcher_v1.features import FEATURE_COLUMNS, assert_no_leakage, build_feature_audit
from historical_models.pitcher_v1.metadata import ModelMetadata
from historical_models.pitcher_v1.model import CANDIDATES, build_pipeline
from historical_models.pitcher_v1.persistence import append_experiment_record, save_all_artifacts


def run_training(warehouse_path: Optional[Path] = None, output_dir: Optional[Path] = None, seed: int = DEFAULT_SEED) -> dict:
    import pandas as pd

    output_dir = Path(output_dir or DEFAULT_ARTIFACT_DIR)
    all_pitcher_rows = pd.read_parquet(warehouse_path or DEFAULT_WAREHOUSE_PITCHER_PARQUET)
    starters = load_starting_pitcher_dataset(warehouse_path)
    train_df, val_df, test_df = chronological_split(starters)
    summary = build_dataset_summary(all_pitcher_rows, starters, train_df, val_df, test_df)

    assert_no_leakage(FEATURE_COLUMNS)
    feature_audit = build_feature_audit(all_pitcher_rows)

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN]
    X_val, y_val = val_df[FEATURE_COLUMNS], val_df[TARGET_COLUMN]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[TARGET_COLUMN]

    experiment_records, all_results = [], []
    best = None
    for spec in CANDIDATES:
        for params in spec.param_grid:
            pipeline = build_pipeline(spec, params)
            pipeline.fit(X_train, y_train)
            val_pred = pipeline.predict(X_val)
            metrics = compute_primary_metrics(y_val.to_numpy(), val_pred)
            experiment_id = f"{spec.name}__{'_'.join(f'{k}={v}' for k, v in params.items()) or 'default'}"
            record = {
                "experiment_id": experiment_id, "feature_set": "v1_always_pregame", "model": spec.name, "params": params,
                "validation_MAE": metrics["mae"], "validation_RMSE": metrics["rmse"], "validation_corr": metrics["pearson"],
            }
            experiment_records.append(record)
            all_results.append({"spec": spec, "params": params, "pipeline": pipeline, "val_metrics": metrics, "experiment_id": experiment_id})
            if best is None or metrics["mae"] < best["val_metrics"]["mae"]:
                best = all_results[-1]

    # FREEZE -- evaluate the selected pipeline exactly once on TEST.
    frozen_pipeline = best["pipeline"]
    test_pred = frozen_pipeline.predict(X_test)
    test_metrics = compute_primary_metrics(y_test.to_numpy(), test_pred)

    test_with_preds = test_df.copy()
    test_with_preds["prediction"] = test_pred
    top5 = compute_topn_metrics(test_with_preds, 5)
    top10 = compute_topn_metrics(test_with_preds, 10)
    top_decile_actual_avg = compute_top_decile_actual_avg(test_with_preds)
    calibration = compute_calibration_table(test_with_preds)
    buckets = compute_bucket_analysis(test_with_preds)
    outliers = compute_outliers(test_with_preds, n=10)

    # Feature importance on VALIDATION (never test) -- test stays clean for the final report only.
    importance = compute_permutation_importance(frozen_pipeline, X_val, y_val, seed=seed, n_repeats=8)

    mean_row = next(r for r in all_results if r["spec"].name == "mean_baseline")
    mean_val_metrics = mean_row["val_metrics"]
    mean_test_pred = mean_row["pipeline"].predict(X_test)
    mean_test_metrics = compute_primary_metrics(y_test.to_numpy(), mean_test_pred)
    mae_improvement_pct = round((mean_test_metrics["mae"] - test_metrics["mae"]) / mean_test_metrics["mae"] * 100, 2) if mean_test_metrics["mae"] else None
    rmse_improvement_pct = round((mean_test_metrics["rmse"] - test_metrics["rmse"]) / mean_test_metrics["rmse"] * 100, 2) if mean_test_metrics["rmse"] else None

    metadata = ModelMetadata(feature_list=FEATURE_COLUMNS, model_type=best["spec"].name, hyperparameters=best["params"], seed=seed)

    artifact_paths = save_all_artifacts(
        output_dir, frozen_pipeline, metadata.to_dict(), FEATURE_COLUMNS,
        validation_metrics=best["val_metrics"], test_metrics=test_metrics,
        feature_importance=importance, calibration=calibration, outliers=outliers,
    )
    for record in experiment_records:
        append_experiment_record(output_dir, record)

    return {
        "dataset_summary": summary,
        "feature_audit": feature_audit,
        "missingness_by_family": missingness_by_family(starters),
        "experiment_records": experiment_records,
        "selected": {"model": best["spec"].name, "params": best["params"], "experiment_id": best["experiment_id"]},
        "validation_metrics": best["val_metrics"],
        "test_metrics": test_metrics,
        "top5": top5, "top10": top10, "top_decile_actual_avg": top_decile_actual_avg,
        "calibration": calibration, "buckets": buckets, "outliers": outliers,
        "feature_importance": importance,
        "mean_baseline_validation_metrics": mean_val_metrics,
        "mean_baseline_test_metrics": mean_test_metrics,
        "mae_improvement_pct": mae_improvement_pct, "rmse_improvement_pct": rmse_improvement_pct,
        "artifact_paths": {k: str(v) for k, v in artifact_paths.items()},
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Big Money DFS Historical Pitcher Model V1.")
    parser.add_argument("--warehouse-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    result = run_training(args.warehouse_path, args.output_dir, args.seed)
    import json

    print(json.dumps({
        "status": "ok",
        "train_rows": result["dataset_summary"].train_rows,
        "validation_rows": result["dataset_summary"].validation_rows,
        "test_rows": result["dataset_summary"].test_rows,
        "selected_model": result["selected"]["model"],
        "test_mae": result["test_metrics"]["mae"],
        "mean_baseline_test_mae": result["mean_baseline_test_metrics"]["mae"],
        "mae_improvement_pct": result["mae_improvement_pct"],
        "output_dir": result["output_dir"],
    }, default=str))


if __name__ == "__main__":
    main()
