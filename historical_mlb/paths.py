"""Milestone 32.1 -- warehouse directory layout (Part 3). Single source
of truth for every path the build pipeline reads/writes, so the layout
is defined once, not scattered across modules.

All of data/historical/ is gitignored (see M32.0's .gitignore entry --
still covers this whole tree). Nothing under here is ever committed.
"""

from pathlib import Path

WAREHOUSE_ROOT = Path("data/historical/mlb")

RAW_MLB_DIR = WAREHOUSE_ROOT / "raw" / "mlb"
RAW_STATCAST_DIR = WAREHOUSE_ROOT / "raw" / "statcast"
RAW_WEATHER_DIR = WAREHOUSE_ROOT / "raw" / "weather"

PROCESSED_DIR = WAREHOUSE_ROOT / "processed"
GAMES_PARQUET = PROCESSED_DIR / "games.parquet"
HITTER_FEATURES_PARQUET = PROCESSED_DIR / "hitter_game_features.parquet"
PITCHER_FEATURES_PARQUET = PROCESSED_DIR / "pitcher_game_features.parquet"
WEATHER_PARQUET = PROCESSED_DIR / "weather.parquet"

CROSSWALKS_DIR = WAREHOUSE_ROOT / "crosswalks"
PLAYERS_PARQUET = CROSSWALKS_DIR / "players.parquet"
VENUES_PARQUET = CROSSWALKS_DIR / "venues.parquet"

STATE_DIR = WAREHOUSE_ROOT / "state"
CHECKPOINTS_DIR = STATE_DIR / "checkpoints"
BUILD_METADATA_PATH = STATE_DIR / "build_metadata.json"

REPORTS_DIR = WAREHOUSE_ROOT / "reports"
COVERAGE_REPORT_PATH = REPORTS_DIR / "coverage.json"
QUALITY_REPORT_PATH = REPORTS_DIR / "quality.json"
BUILD_REPORT_PATH = REPORTS_DIR / "build_report.json"

FEATURE_MANIFEST_PATH = REPORTS_DIR / "feature_manifest.json"

WAREHOUSE_VERSION = "mlb_feature_warehouse_v1"


def ensure_directories() -> None:
    for d in (
        RAW_MLB_DIR, RAW_STATCAST_DIR, RAW_WEATHER_DIR, PROCESSED_DIR,
        CROSSWALKS_DIR, CHECKPOINTS_DIR, REPORTS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
