"""Typed data models for actual (post-lock) DraftKings contest ownership.

`actual_ownership` is observed contest data -- the opposite of
ownership/models.py's OwnershipProjection, which is always a MODEL
PREDICTION. The two must never be confused; see evaluation/ownership_evaluator.py
for where they're finally joined (read-only, never written back into
either source).
"""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ContestMetadata:
    """Best-effort contest identity. Most DraftKings result exports do
    not embed contest name/type/max-entries in the file body at all --
    fields that can't be determined stay None rather than being guessed."""

    contest_id: Optional[str]
    contest_name: Optional[str]
    contest_type: Optional[str]
    entries: Optional[int]
    max_entries: Optional[int]
    results_filename: str
    source_file_hash: str
    retrieved_at_utc: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActualOwnershipRecord:
    """One player's OBSERVED ownership in one specific contest. Never
    named actual_ownership anywhere but here and in the field itself --
    see the module docstring."""

    dk_player_id: Optional[str]
    mlb_player_id: Optional[str]
    name: str
    team: Optional[str]
    player_type: Optional[str]

    actual_ownership: float  # percentage points, e.g. 17.5 means 17.5% -- never 0.175

    contest_id: Optional[str]
    contest_name: Optional[str]
    contest_size: Optional[int]
    source_file: str

    match_status: str  # "matched" | "unmatched" | "ambiguous"
    match_confidence: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
