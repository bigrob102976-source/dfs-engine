"""NFL M9 -- immutable persistence for the real NFL projection training
dataset. Local disk only (Parquet files bypass research/artifact_storage.py's
R2-capable JSON abstraction -- that module has no Parquet writer, and
building one is out of this milestone's scope; metadata/feature-list/
quality-report stay JSON through the existing save_json/raise_if_exists
discipline, matching every other NFL persistence module).

    historical/nfl/training/projections/v1/{season}/{timestamp}/
      metadata.json
      feature_list.json
      quality_report.json
      {split}_offense.parquet
      {split}_dst.parquet

Offense and DST rows are written to SEPARATE Parquet files per split
(never combined into one file): they have genuinely different schemas
(gsis_id vs. team-only identity, different feature sets -- see nfl/
training_dataset.py's module docstring on why DST is a separate row
type), and polars' dict-to-DataFrame schema inference cannot reconcile
heterogeneous row shapes within a single column set."""

from pathlib import Path
from typing import Dict, List

import polars as pl

from research.artifact_storage import raise_if_exists
from research.storage import save_json

from nfl.training_dataset import NflDstTrainingRow, NflOffenseTrainingRow, SPLIT_TEST, SPLIT_TRAIN, SPLIT_VALIDATION

DEFAULT_TRAINING_ROOT = Path(__file__).resolve().parent.parent / "historical" / "nfl" / "training" / "projections" / "v1"


def _rows_to_dicts(rows: List) -> List[dict]:
    return [r.to_dict() for r in rows]


def _write_split_files(rows_by_key: List[dict], base: Path, prefix: str) -> Dict[str, Path]:
    import json

    written: Dict[str, Path] = {}
    for split_name in (SPLIT_TRAIN, SPLIT_VALIDATION, SPLIT_TEST):
        split_rows = [dict(r) for r in rows_by_key if r["split"] == split_name]
        path = base / f"{split_name}_{prefix}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if split_rows:
            # Nested dict columns (rolling_features/season_to_date_features)
            # don't round-trip through polars' native dict-column inference
            # reliably across many heterogeneous real rows, so each row's
            # nested feature dicts are JSON-encoded into one string column --
            # readers json.loads() it back. Every scalar column stays
            # natively typed.
            for r in split_rows:
                for key in ("rolling_features", "season_to_date_features"):
                    if key in r:
                        r[key] = json.dumps(r[key])
            df = pl.DataFrame(split_rows)
        else:
            df = pl.DataFrame()
        df.write_parquet(path)
        written[f"{split_name}_{prefix}"] = path
    return written


def save_training_dataset(
    offense_rows: List[NflOffenseTrainingRow], dst_rows: List[NflDstTrainingRow],
    metadata: dict, feature_list: dict, quality_report: dict,
    season: int, timestamp: str, output_root: Path = DEFAULT_TRAINING_ROOT,
) -> Dict[str, Path]:
    base = Path(output_root) / str(season) / timestamp
    expected_files = ["metadata.json", "feature_list.json", "quality_report.json"]
    for split_name in (SPLIT_TRAIN, SPLIT_VALIDATION, SPLIT_TEST):
        expected_files += [f"{split_name}_offense.parquet", f"{split_name}_dst.parquet"]
    for name in expected_files:
        raise_if_exists(base / name)

    save_json(base / "metadata.json", metadata)
    save_json(base / "feature_list.json", feature_list)
    save_json(base / "quality_report.json", quality_report)

    written: Dict[str, Path] = {"metadata": base / "metadata.json", "feature_list": base / "feature_list.json", "quality_report": base / "quality_report.json"}
    written.update(_write_split_files(_rows_to_dicts(offense_rows), base, "offense"))
    written.update(_write_split_files(_rows_to_dicts(dst_rows), base, "dst"))
    return written
