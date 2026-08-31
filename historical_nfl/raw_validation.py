"""NFL M6A Phase 4/7 -- per-dataset schema validation and the compact
data-quality report. Every real nflverse column name below was confirmed
by directly inspecting a live nflreadpy 0.1.5 response (season 2025) --
none is invented; see the M6A final report for the exact inspection
commands run.

Validation NEVER drops a row. `DatasetValidationResult` reports counts
(duplicates, missing identity, invalid numerics); the caller decides
what to do with a non-empty report. `passed` reflects only the
STRUCTURAL contract (are the columns this dataset needs even present) --
a real data-quality anomaly (a duplicate key, a missing GSIS ID) is
reported, not treated as an ingestion failure, matching this project's
"report, don't silently drop or refuse" discipline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional

import polars as pl

SCHEDULES_REQUIRED_COLUMNS = ["season", "week", "game_id", "home_team", "away_team", "gameday"]
ROSTERS_REQUIRED_COLUMNS = ["season", "week", "gsis_id", "full_name", "team", "position"]
WEEKLY_PLAYER_STATS_REQUIRED_COLUMNS = [
    "season", "week", "player_id", "team", "position",
    "completions", "attempts", "passing_yards", "passing_tds",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
]
TEAM_STATS_REQUIRED_COLUMNS = ["season", "week", "team", "opponent_team"]
PLAY_BY_PLAY_REQUIRED_COLUMNS = [
    "game_id", "play_id", "season", "week", "posteam", "defteam",
    "epa", "yardline_100", "down", "ydstogo",
]
# NFL M6C: real columns confirmed live against nflreadpy 0.1.5 season 2025.
SNAP_COUNTS_REQUIRED_COLUMNS = [
    "season", "week", "game_id", "pfr_player_id", "player", "team", "position",
    "offense_snaps", "offense_pct", "defense_snaps", "defense_pct", "st_snaps", "st_pct",
]
# season/week are DERIVED by historical_nfl/nflverse_client.py::fetch_participation
# (parsed from nflverse_game_id) -- the real source schema has neither.
PARTICIPATION_REQUIRED_COLUMNS = [
    "season", "week", "nflverse_game_id", "play_id", "possession_team",
    "offense_players", "defense_players", "n_offense", "n_defense", "route",
]

WEEKLY_PLAYER_STATS_NUMERIC_FIELDS = [
    "passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
    "receiving_yards", "receiving_tds", "targets", "receptions",
    "fantasy_points", "fantasy_points_ppr",
]
TEAM_STATS_NUMERIC_FIELDS = ["passing_yards", "rushing_yards", "passing_tds", "rushing_tds"]
PLAY_BY_PLAY_NUMERIC_FIELDS = ["epa", "yardline_100", "down", "ydstogo"]
SNAP_COUNTS_NUMERIC_FIELDS = ["offense_snaps", "offense_pct", "defense_snaps", "defense_pct", "st_snaps", "st_pct"]


@dataclass
class DatasetValidationResult:
    dataset_name: str
    season: int
    week: Optional[int]
    row_count: int
    missing_required_columns: List[str]
    duplicate_key_count: int
    missing_identity_count: int
    invalid_numeric_count: int
    unique_players: Optional[int]
    unique_teams: Optional[int]
    unique_games: Optional[int]

    @property
    def passed(self) -> bool:
        return not self.missing_required_columns

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


def _missing_columns(df: pl.DataFrame, required: List[str]) -> List[str]:
    return [c for c in required if c not in df.columns]


def _duplicate_count(df: pl.DataFrame, key_columns: List[str]) -> int:
    if any(c not in df.columns for c in key_columns) or df.height == 0:
        return 0
    return int(df.select(pl.struct(key_columns).is_duplicated().alias("_dup")).to_series().sum())


def _invalid_numeric_count(df: pl.DataFrame, numeric_fields: List[str]) -> int:
    """Counts ROWS with at least one NaN/Infinite value among the
    present numeric fields (real, IEEE-float corruption -- distinct from
    a legitimate null/missing value, which is not an error)."""
    present = [c for c in numeric_fields if c in df.columns and df.schema[c] in (pl.Float32, pl.Float64)]
    if not present or df.height == 0:
        return 0
    bad = pl.any_horizontal([pl.col(c).is_nan() | pl.col(c).is_infinite() for c in present])
    return int(df.select(bad.alias("_bad")).to_series().sum())


def _unique_non_null(df: pl.DataFrame, column: str) -> Optional[int]:
    if column not in df.columns:
        return None
    return int(df.filter(pl.col(column).is_not_null()).select(pl.col(column).n_unique()).item())


def validate_schedules(df: pl.DataFrame, season: int) -> DatasetValidationResult:
    missing = _missing_columns(df, SCHEDULES_REQUIRED_COLUMNS)
    duplicate_key_count = 0 if missing else _duplicate_count(df, ["game_id"])
    unique_teams = None
    if not missing:
        unique_teams = pl.concat([df["home_team"], df["away_team"]]).n_unique()
    return DatasetValidationResult(
        dataset_name="schedules", season=season, week=None, row_count=df.height,
        missing_required_columns=missing, duplicate_key_count=duplicate_key_count,
        missing_identity_count=0, invalid_numeric_count=0,
        unique_players=None, unique_teams=unique_teams,
        unique_games=_unique_non_null(df, "game_id"),
    )


def validate_rosters(df: pl.DataFrame, season: int, week: Optional[int]) -> DatasetValidationResult:
    missing = _missing_columns(df, ROSTERS_REQUIRED_COLUMNS)
    if missing:
        return DatasetValidationResult(
            dataset_name="rosters", season=season, week=week, row_count=df.height,
            missing_required_columns=missing, duplicate_key_count=0, missing_identity_count=0,
            invalid_numeric_count=0, unique_players=None, unique_teams=None, unique_games=None,
        )
    has_gsis = df.filter((pl.col("gsis_id").is_not_null()) & (pl.col("gsis_id") != ""))
    missing_identity_count = df.height - has_gsis.height
    duplicate_key_count = _duplicate_count(has_gsis, ["season", "week", "team", "gsis_id"])
    return DatasetValidationResult(
        dataset_name="rosters", season=season, week=week, row_count=df.height,
        missing_required_columns=[], duplicate_key_count=duplicate_key_count,
        missing_identity_count=missing_identity_count, invalid_numeric_count=0,
        unique_players=has_gsis.select(pl.col("gsis_id").n_unique()).item() if has_gsis.height else 0,
        unique_teams=_unique_non_null(df, "team"), unique_games=None,
    )


def validate_weekly_player_stats(df: pl.DataFrame, season: int, week: Optional[int]) -> DatasetValidationResult:
    missing = _missing_columns(df, WEEKLY_PLAYER_STATS_REQUIRED_COLUMNS)
    if missing:
        return DatasetValidationResult(
            dataset_name="weekly_player_stats", season=season, week=week, row_count=df.height,
            missing_required_columns=missing, duplicate_key_count=0, missing_identity_count=0,
            invalid_numeric_count=0, unique_players=None, unique_teams=None, unique_games=None,
        )
    has_id = df.filter(pl.col("player_id").is_not_null())
    missing_identity_count = df.height - has_id.height
    duplicate_key_count = _duplicate_count(has_id, ["season", "week", "player_id", "team"])
    return DatasetValidationResult(
        dataset_name="weekly_player_stats", season=season, week=week, row_count=df.height,
        missing_required_columns=[], duplicate_key_count=duplicate_key_count,
        missing_identity_count=missing_identity_count,
        invalid_numeric_count=_invalid_numeric_count(df, WEEKLY_PLAYER_STATS_NUMERIC_FIELDS),
        unique_players=_unique_non_null(df, "player_id"), unique_teams=_unique_non_null(df, "team"),
        unique_games=_unique_non_null(df, "game_id"),
    )


def validate_team_stats(df: pl.DataFrame, season: int, week: Optional[int]) -> DatasetValidationResult:
    missing = _missing_columns(df, TEAM_STATS_REQUIRED_COLUMNS)
    duplicate_key_count = 0 if missing else _duplicate_count(df, ["season", "week", "team"])
    return DatasetValidationResult(
        dataset_name="team_stats", season=season, week=week, row_count=df.height,
        missing_required_columns=missing, duplicate_key_count=duplicate_key_count,
        missing_identity_count=0,
        invalid_numeric_count=0 if missing else _invalid_numeric_count(df, TEAM_STATS_NUMERIC_FIELDS),
        unique_players=None, unique_teams=None if missing else _unique_non_null(df, "team"),
        unique_games=None if missing else _unique_non_null(df, "game_id"),
    )


def validate_play_by_play(df: pl.DataFrame, season: int, week: Optional[int]) -> DatasetValidationResult:
    missing = _missing_columns(df, PLAY_BY_PLAY_REQUIRED_COLUMNS)
    duplicate_key_count = 0 if missing else _duplicate_count(df, ["game_id", "play_id"])
    return DatasetValidationResult(
        dataset_name="play_by_play", season=season, week=week, row_count=df.height,
        missing_required_columns=missing, duplicate_key_count=duplicate_key_count,
        missing_identity_count=0,
        invalid_numeric_count=0 if missing else _invalid_numeric_count(df, PLAY_BY_PLAY_NUMERIC_FIELDS),
        unique_players=None, unique_teams=None if missing else _unique_non_null(df, "posteam"),
        unique_games=None if missing else _unique_non_null(df, "game_id"),
    )


def validate_snap_counts(df: pl.DataFrame, season: int, week: Optional[int]) -> DatasetValidationResult:
    missing = _missing_columns(df, SNAP_COUNTS_REQUIRED_COLUMNS)
    if missing:
        return DatasetValidationResult(
            dataset_name="snap_counts", season=season, week=week, row_count=df.height,
            missing_required_columns=missing, duplicate_key_count=0, missing_identity_count=0,
            invalid_numeric_count=0, unique_players=None, unique_teams=None, unique_games=None,
        )
    has_id = df.filter(pl.col("pfr_player_id").is_not_null())
    missing_identity_count = df.height - has_id.height
    duplicate_key_count = _duplicate_count(has_id, ["season", "week", "game_id", "pfr_player_id"])
    return DatasetValidationResult(
        dataset_name="snap_counts", season=season, week=week, row_count=df.height,
        missing_required_columns=[], duplicate_key_count=duplicate_key_count,
        missing_identity_count=missing_identity_count,
        invalid_numeric_count=_invalid_numeric_count(df, SNAP_COUNTS_NUMERIC_FIELDS),
        unique_players=_unique_non_null(df, "pfr_player_id"), unique_teams=_unique_non_null(df, "team"),
        unique_games=_unique_non_null(df, "game_id"),
    )


def validate_participation(df: pl.DataFrame, season: int, week: Optional[int]) -> DatasetValidationResult:
    missing = _missing_columns(df, PARTICIPATION_REQUIRED_COLUMNS)
    if missing:
        return DatasetValidationResult(
            dataset_name="participation", season=season, week=week, row_count=df.height,
            missing_required_columns=missing, duplicate_key_count=0, missing_identity_count=0,
            invalid_numeric_count=0, unique_players=None, unique_teams=None, unique_games=None,
        )
    duplicate_key_count = _duplicate_count(df, ["nflverse_game_id", "play_id"])
    # "identity" here means a play with genuinely no offense_players list at
    # all (e.g. a non-offensive-snap row) -- not a per-player identity concept.
    missing_identity_count = df.filter((pl.col("offense_players").is_null()) | (pl.col("offense_players") == "")).height
    return DatasetValidationResult(
        dataset_name="participation", season=season, week=week, row_count=df.height,
        missing_required_columns=[], duplicate_key_count=duplicate_key_count,
        missing_identity_count=missing_identity_count, invalid_numeric_count=0,
        unique_players=None, unique_teams=_unique_non_null(df, "possession_team"),
        unique_games=_unique_non_null(df, "nflverse_game_id"),
    )
