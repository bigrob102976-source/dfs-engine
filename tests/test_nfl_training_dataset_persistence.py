"""NFL M9 -- targeted tests for nfl/training_dataset_persistence.py."""

import pytest
import polars as pl

from nfl.training_dataset import NflOffenseTrainingRow, SCHEMA_VERSION, SPLIT_TEST, SPLIT_TRAIN, SPLIT_VALIDATION, TARGET_SCORING_VERSION
from nfl.training_dataset_persistence import save_training_dataset

SEASON = 2025
TS = "20260904T000000000000"


def _row(split=SPLIT_TRAIN, week=6):
    return NflOffenseTrainingRow(
        schema_version=SCHEMA_VERSION, target_scoring_version=TARGET_SCORING_VERSION,
        season=SEASON, week=week, game_id="g1", gsis_id="00-1", canonical_player_id=None,
        position="RB", team="PHI", opponent="DAL", home_away="home", rest_days=7,
        feature_as_of_season=SEASON, feature_as_of_week=week,
        rolling_features={"carries_mean_last1": 10.0}, season_to_date_features={"carries_season_mean": 10.0},
        has_prior_week=True, weeks_of_history=1, salary=None, injury_report_status=None,
        target_dk_points=12.5, target_scored=True, split=split,
    )


def test_save_writes_all_expected_files(tmp_path):
    paths = save_training_dataset([_row()], [], {"seasons": [2025]}, {"features": []}, {"rows": 1}, SEASON, TS, output_root=tmp_path)
    expected = ["metadata", "feature_list", "quality_report"]
    for split in (SPLIT_TRAIN, SPLIT_VALIDATION, SPLIT_TEST):
        expected += [f"{split}_offense", f"{split}_dst"]
    for key in expected:
        assert paths[key].exists()


def test_save_never_overwrites(tmp_path):
    save_training_dataset([_row()], [], {}, {}, {}, SEASON, TS, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_training_dataset([_row()], [], {}, {}, {}, SEASON, TS, output_root=tmp_path)


def test_rows_land_in_correct_split_file(tmp_path):
    train_row = _row(split=SPLIT_TRAIN, week=1)
    test_row = _row(split=SPLIT_TEST, week=17)
    paths = save_training_dataset([train_row, test_row], [], {}, {}, {}, SEASON, TS, output_root=tmp_path)
    train_df = pl.read_parquet(paths[f"{SPLIT_TRAIN}_offense"])
    test_df = pl.read_parquet(paths[f"{SPLIT_TEST}_offense"])
    assert train_df.height == 1
    assert test_df.height == 1
    assert train_df["week"][0] == 1
    assert test_df["week"][0] == 17


def test_empty_split_still_writes_a_file(tmp_path):
    paths = save_training_dataset([_row(split=SPLIT_TRAIN)], [], {}, {}, {}, SEASON, TS, output_root=tmp_path)
    assert paths[f"{SPLIT_VALIDATION}_offense"].exists()
    assert paths[f"{SPLIT_VALIDATION}_dst"].exists()
