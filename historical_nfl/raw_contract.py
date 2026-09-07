"""NFL M6A Phase 2/5 -- the source-preserving raw ingestion contract.

Every raw nflverse snapshot this package persists carries this exact
metadata envelope alongside the untouched source rows. Raw ingestion
performs NO feature engineering, NO joins across datasets, and NO
renaming of source fields -- see historical_nfl/raw_persistence.py's
document shape.

Temporal metadata (M6 Phase 9 leakage-prevention rules, prepared for by
M6A Phase 5):
  - event_time: the real-world moment the data describes -- left null at
    the SNAPSHOT-metadata level for every M6A dataset, deliberately: a
    snapshot here always spans a whole season (or week), never a single
    moment, so reducing it to one scalar timestamp would misrepresent
    it. The real per-event timestamps nflverse does supply (e.g.
    schedules' own `gameday`/`gametime` columns, one real kickoff per
    row) are preserved verbatim in the row data itself and are exactly
    what a future per-game feature-row (M6F) should read -- this field
    exists so a future dataset with a genuine single-moment-per-snapshot
    shape (e.g. one injury report pull) has somewhere honest to put it.
  - available_at: the moment this data was actually knowable/published.
    nflverse does NOT supply a true publication timestamp distinct from
    "when we happened to fetch it" for any of these five datasets --
    this is always null here, deliberately, per M6's explicit "never
    fabricate timestamps" instruction. A future milestone with a real
    publication-timestamped source (e.g. a live injury report feed)
    would populate this honestly; backfilling it here would not be
    honest, since we have no such signal today.
  - ingested_at: exactly equal to fetched_at -- one real observation,
    described under both this contract's and M6's own vocabulary.
"""

from dataclasses import asdict, dataclass
from typing import Optional

SPORT = "NFL"
SOURCE = "NFLVERSE"

DATASET_SCHEDULES = "schedules"
DATASET_ROSTERS = "rosters"
DATASET_WEEKLY_PLAYER_STATS = "weekly_player_stats"
DATASET_TEAM_STATS = "team_stats"
DATASET_PLAY_BY_PLAY = "play_by_play"
DATASET_SNAP_COUNTS = "snap_counts"
DATASET_PARTICIPATION = "participation"

SCHEMA_VERSION = "nflverse_raw_v1"


@dataclass
class NflverseRawSnapshotMetadata:
    sport: str
    source: str
    source_provenance: str
    dataset_name: str
    season: int
    week: Optional[int]
    fetched_at: str
    data_timestamp: Optional[str]
    event_time: Optional[str]
    available_at: Optional[str]
    ingested_at: str
    schema_version: str
    row_count: int

    def to_dict(self) -> dict:
        return asdict(self)
