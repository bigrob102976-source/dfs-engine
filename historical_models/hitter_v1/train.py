"""Milestone 32.3 -- training pipeline entry point.

    python -m historical_models.hitter_v1.train [--warehouse-path P] [--output-dir D] [--seed N]

Runs candidate models against BOTH feature-availability experiments
(ALWAYS_PREGAME and AFTER_LINEUP) on VALIDATION only, selects the
single best (model x feature-availability-class) by validation MAE,
FREEZES it, then evaluates that frozen pipeline exactly ONCE on the
untouched TEST set. Nothing after the test evaluation feeds back into
model/feature selection -- same "FINAL TEST DISCIPLINE" as Pitcher
Model V1.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import pandas as pd

from historical_models.hitter_v1.config import AFTER_LINEUP, ALWAYS_PREGAME, DEFAULT_ARTIFACT_DIR, DEFAULT_SEED, DEFAULT_WAREHOUSE_HITTER_PARQUET, TARGET_COLUMN
from historical_models.hitter_v1.dataset import (
    build_dataset_summary, chronological_split, load_hitter_dataset, missingness_by_family, target_distribution_summary,
)
from historical_models.hitter_v1.evaluate import (
    compute_batting_order_analysis, compute_calibration_table, compute_ceiling_analysis, compute_low_score_analysis,
    compute_outliers, compute_park_analysis, compute_permutation_importance, compute_platoon_analysis,
    compute_primary_metrics, compute_top_decile_actual_avg, compute_topn_metrics,
)
from historical_models.hitter_v1.features import assert_no_leakage, build_feature_audit, categorical_columns_for, feature_columns_for, numeric_columns_for
from historical_models.hitter_v1.metadata import ModelMetadata
from historical_models.hitter_v1.model import CANDIDATES, build_pipeline
from historical_models.hitter_v1.persistence import append_experiment_record, save_all_artifacts


def run_training(warehouse_path: Optional[Path] = None, output_dir: Optional[Path] = None, seed: int = DEFAULT_SEED) -> dict:
    output_dir = Path(output_dir or DEFAULT_ARTIFACT_DIR)
    df = load_hitter_dataset(warehouse_path)
    train_df, val_df, test_df = chronological_split(df)
    summary = build_dataset_summary(df, train_df, val_df, test_df)
    target_dist = target_distribution_summary(df)

    for cls in (ALWAYS_PREGAME, AFTER_LINEUP):
        assert_no_leakage(feature_columns_for(cls))

    feature_audit = build_feature_audit(df)

    experiment_records = []
    all_results = []
    for cls in (ALWAYS_PREGAME, AFTER_LINEUP):
        numeric_cols, categorical_cols = numeric_columns_for(cls), categorical_columns_for(cls)
        feature_cols = feature_columns_for(cls)
        X_train, y_train = train_df[feature_cols], train_df[TARGET_COLUMN]
        X_val, y_val = val_df[feature_cols], val_df[TARGET_COLUMN]

        for spec in CANDIDATES:
            for params in spec.param_grid:
                pipeline = build_pipeline(spec, params, numeric_cols, categorical_cols)
                pipeline.fit(X_train, y_train)
                val_pred = pipeline.predict(X_val)
                metrics = compute_primary_metrics(y_val.to_numpy(), val_pred)
                experiment_id = f"{cls}__{spec.name}__{'_'.join(f'{k}={v}' for k, v in params.items()) or 'default'}"
                record = {
                    "experiment_id": experiment_id, "feature_availability_class": cls, "feature_set_size": len(feature_cols),
                    "model": spec.name, "params": params, "train_rows": len(X_train), "validation_rows": len(X_val),
                    "validation_MAE": metrics["mae"], "validation_RMSE": metrics["rmse"],
                    "validation_pearson": metrics["pearson"], "validation_spearman": metrics["spearman"], "validation_r2": metrics["r2"],
                }
                experiment_records.append(record)
                all_results.append({
                    "cls": cls, "spec": spec, "params": params, "pipeline": pipeline, "val_metrics": metrics,
                    "experiment_id": experiment_id, "numeric_cols": numeric_cols, "categorical_cols": categorical_cols,
                    "feature_cols": feature_cols,
                })

    best = min(all_results, key=lambda r: r["val_metrics"]["mae"])
    best_cls_by_class = {}
    for cls in (ALWAYS_PREGAME, AFTER_LINEUP):
        cls_results = [r for r in all_results if r["cls"] == cls]
        best_cls_by_class[cls] = min(cls_results, key=lambda r: r["val_metrics"]["mae"])

    # FREEZE -- evaluate the selected pipeline exactly once on TEST.
    frozen = best
    X_test, y_test = test_df[frozen["feature_cols"]], test_df[TARGET_COLUMN]
    test_pred = frozen["pipeline"].predict(X_test)
    test_metrics = compute_primary_metrics(y_test.to_numpy(), test_pred)

    test_with_preds = test_df.copy()
    test_with_preds["prediction"] = test_pred
    top5 = compute_topn_metrics(test_with_preds, 5)
    top10 = compute_topn_metrics(test_with_preds, 10)
    top20 = compute_topn_metrics(test_with_preds, 20)
    top_decile_actual_avg = compute_top_decile_actual_avg(test_with_preds)
    calibration = compute_calibration_table(test_with_preds)
    low_score = compute_low_score_analysis(test_with_preds)
    ceiling = compute_ceiling_analysis(test_with_preds)
    batting_order = compute_batting_order_analysis(test_with_preds)
    platoon = compute_platoon_analysis(test_with_preds)
    park = compute_park_analysis(test_with_preds)
    outliers = compute_outliers(test_with_preds, n=20, has_batting_order=(frozen["cls"] == AFTER_LINEUP))

    X_val_frozen, y_val_frozen = val_df[frozen["feature_cols"]], val_df[TARGET_COLUMN]
    importance = compute_permutation_importance(frozen["pipeline"], X_val_frozen, y_val_frozen, seed=seed, n_repeats=5)

    mean_row = next(r for r in all_results if r["spec"].name == "mean_baseline" and r["cls"] == frozen["cls"])
    mean_val_metrics = mean_row["val_metrics"]
    mean_test_pred = mean_row["pipeline"].predict(X_test)
    mean_test_metrics = compute_primary_metrics(y_test.to_numpy(), mean_test_pred)
    mae_improvement_pct = round((mean_test_metrics["mae"] - test_metrics["mae"]) / mean_test_metrics["mae"] * 100, 2) if mean_test_metrics["mae"] else None
    rmse_improvement_pct = round((mean_test_metrics["rmse"] - test_metrics["rmse"]) / mean_test_metrics["rmse"] * 100, 2) if mean_test_metrics["rmse"] else None

    metadata = ModelMetadata(
        feature_availability_class=frozen["cls"], feature_list=frozen["feature_cols"],
        model_type=frozen["spec"].name, hyperparameters=frozen["params"], seed=seed,
    )

    artifact_paths = save_all_artifacts(
        output_dir, frozen["pipeline"], metadata.to_dict(), frozen["feature_cols"],
        validation_metrics=frozen["val_metrics"], test_metrics=test_metrics,
        feature_importance=importance, calibration=calibration, ceiling_analysis=ceiling, outliers=outliers,
    )
    for record in experiment_records:
        append_experiment_record(output_dir, record)

    return {
        "dataset_summary": summary, "target_distribution": target_dist, "feature_audit": feature_audit,
        "missingness_always_pregame": missingness_by_family(df, feature_columns_for(ALWAYS_PREGAME)),
        "missingness_after_lineup": missingness_by_family(df, feature_columns_for(AFTER_LINEUP)),
        "experiment_records": experiment_records,
        "best_by_class": {cls: {"model": r["spec"].name, "params": r["params"], "validation_MAE": r["val_metrics"]["mae"]} for cls, r in best_cls_by_class.items()},
        "selected": {"model": frozen["spec"].name, "params": frozen["params"], "feature_availability_class": frozen["cls"], "experiment_id": frozen["experiment_id"]},
        "validation_metrics": frozen["val_metrics"], "test_metrics": test_metrics,
        "top5": top5, "top10": top10, "top20": top20, "top_decile_actual_avg": top_decile_actual_avg,
        "calibration": calibration, "low_score_analysis": low_score, "ceiling_analysis": ceiling,
        "batting_order_analysis": batting_order, "platoon_analysis": platoon, "park_analysis": park, "outliers": outliers,
        "feature_importance": importance,
        "mean_baseline_validation_metrics": mean_val_metrics, "mean_baseline_test_metrics": mean_test_metrics,
        "mae_improvement_pct": mae_improvement_pct, "rmse_improvement_pct": rmse_improvement_pct,
        "artifact_paths": {k: str(v) for k, v in artifact_paths.items()}, "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Big Money DFS Historical Hitter Model V1.")
    parser.add_argument("--warehouse-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    result = run_training(args.warehouse_path, args.output_dir, args.seed)
    print(json.dumps({
        "status": "ok",
        "train_rows": result["dataset_summary"].train_rows,
        "validation_rows": result["dataset_summary"].validation_rows,
        "test_rows": result["dataset_summary"].test_rows,
        "selected_model": result["selected"]["model"],
        "selected_feature_availability_class": result["selected"]["feature_availability_class"],
        "test_mae": result["test_metrics"]["mae"],
        "mean_baseline_test_mae": result["mean_baseline_test_metrics"]["mae"],
        "mae_improvement_pct": result["mae_improvement_pct"],
        "output_dir": result["output_dir"],
    }, default=str))


if __name__ == "__main__":
    main()
