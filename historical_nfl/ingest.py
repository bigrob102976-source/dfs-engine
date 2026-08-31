"""NFL M6A Phase 6 -- orchestration: fetch (nflverse_client) -> validate
(raw_validation) -> persist (raw_persistence), one function per dataset,
plus ingest_week() for the Phase 8 real integration test.

Every function requires an explicit `season` (and, for the three
week-grain datasets, `week`) -- there is no "ingest everything" entry
point, matching Phase 6's "do not require downloading the entire
history for a single weekly request" instruction.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from historical_nfl import nflverse_client, raw_validation
from historical_nfl.raw_contract import (
    DATASET_PARTICIPATION,
    DATASET_PLAY_BY_PLAY,
    DATASET_ROSTERS,
    DATASET_SCHEDULES,
    DATASET_SNAP_COUNTS,
    DATASET_TEAM_STATS,
    DATASET_WEEKLY_PLAYER_STATS,
    SCHEMA_VERSION,
    SOURCE,
    SPORT,
    NflverseRawSnapshotMetadata,
)
from historical_nfl.raw_persistence import DEFAULT_RAW_ROOT, save_raw_snapshot


@dataclass
class IngestResult:
    dataset_name: str
    season: int
    week: Optional[int]
    path: str
    metadata: dict
    quality_report: dict


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _persist(dataset_name: str, season: int, week: Optional[int], df, fetched_at: str, provenance: str, validation, output_root: Path) -> IngestResult:
    metadata = NflverseRawSnapshotMetadata(
        sport=SPORT, source=SOURCE, source_provenance=provenance, dataset_name=dataset_name,
        season=season, week=week, fetched_at=fetched_at, data_timestamp=None,
        event_time=None, available_at=None, ingested_at=fetched_at,
        schema_version=SCHEMA_VERSION, row_count=df.height,
    )
    path = save_raw_snapshot(dataset_name, season, week, df, metadata, _timestamp(), output_root=output_root)
    quality_report = {**validation.to_dict(), "source": SOURCE, "fetched_at": fetched_at}
    return IngestResult(dataset_name=dataset_name, season=season, week=week, path=str(path), metadata=metadata.to_dict(), quality_report=quality_report)


def ingest_schedules(season: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_schedules(season)
    validation = raw_validation.validate_schedules(df, season)
    return _persist(DATASET_SCHEDULES, season, None, df, fetched_at, provenance, validation, output_root)


def ingest_rosters(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_rosters(season, week)
    validation = raw_validation.validate_rosters(df, season, week)
    return _persist(DATASET_ROSTERS, season, week, df, fetched_at, provenance, validation, output_root)


def ingest_weekly_player_stats(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_weekly_player_stats(season, week)
    validation = raw_validation.validate_weekly_player_stats(df, season, week)
    return _persist(DATASET_WEEKLY_PLAYER_STATS, season, week, df, fetched_at, provenance, validation, output_root)


def ingest_team_stats(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_team_stats(season, week)
    validation = raw_validation.validate_team_stats(df, season, week)
    return _persist(DATASET_TEAM_STATS, season, week, df, fetched_at, provenance, validation, output_root)


def ingest_play_by_play(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_play_by_play(season, week)
    validation = raw_validation.validate_play_by_play(df, season, week)
    return _persist(DATASET_PLAY_BY_PLAY, season, week, df, fetched_at, provenance, validation, output_root)


def ingest_snap_counts(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_snap_counts(season, week)
    validation = raw_validation.validate_snap_counts(df, season, week)
    return _persist(DATASET_SNAP_COUNTS, season, week, df, fetched_at, provenance, validation, output_root)


def ingest_participation(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> IngestResult:
    df, fetched_at, provenance = nflverse_client.fetch_participation(season, week)
    validation = raw_validation.validate_participation(df, season, week)
    return _persist(DATASET_PARTICIPATION, season, week, df, fetched_at, provenance, validation, output_root)


def ingest_week(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> dict:
    """Ingests all five M6A datasets for one season/week -- schedules is
    season-grain (persisted once, reused conceptually across every week
    of that season) but is included here too since the real-data
    integration test (M6A Phase 8) needs all five together."""
    return {
        "schedules": ingest_schedules(season, output_root=output_root),
        "rosters": ingest_rosters(season, week, output_root=output_root),
        "weekly_player_stats": ingest_weekly_player_stats(season, week, output_root=output_root),
        "team_stats": ingest_team_stats(season, week, output_root=output_root),
        "play_by_play": ingest_play_by_play(season, week, output_root=output_root),
    }


def ingest_usage_sources(season: int, week: int, output_root: Path = DEFAULT_RAW_ROOT) -> dict:
    """NFL M6C -- the two new raw datasets this milestone adds, ingested
    the same immutable way as ingest_week()'s five M6A datasets."""
    return {
        "snap_counts": ingest_snap_counts(season, week, output_root=output_root),
        "participation": ingest_participation(season, week, output_root=output_root),
    }
