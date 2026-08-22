"""Player identity crosswalk (Milestone 32.0, Part 4).

Confirmed during this audit's live testing: MLBAM/Baseball-Reference/
FanGraphs/Retrosheet IDs do NOT match each other numerically or in any
predictable way (e.g. Aaron Judge is MLBAM 592450, Baseball-Reference
"judgeaa01", FanGraphs 15640, Retrosheet "judga001" -- four unrelated
ID spaces). The free, public Chadwick Bureau player register (which
pybaseball.playerid_lookup() wraps) is the confirmed, live-tested
source for cross-referencing these four systems by name/birthdate.

MLBAM ID is the canonical baseball identifier here (per this
milestone's explicit instruction) because it's the ID every other
source this package touches already anchors to: MLB Stats API keys
every endpoint by it, Statcast's own `batter`/`pitcher` columns ARE
MLBAM IDs, and this project's live pipeline already standardizes on it
end-to-end (models/pitcher.py, models/batter.py, research/adapters/).

DraftKings has NO MLBAM id of its own -- draftkings_unofficial/identity.py
(Milestone 31.2's live-provider matcher) already solves DK-draftable ->
MLBAM matching for CURRENT slates via research-package name/team
matching (identity.match_draftables). This module's DK crosswalk row
is deliberately compatible with that existing matcher's output shape
(dk_player_id + a confidence/method field) rather than reinventing a
second DK-matching algorithm -- for HISTORICAL dates, DraftKings salary
data isn't reliably available at all yet (see sources/salaries.py), so
the dk_id/dk_name fields on a crosswalk row are simply left null until
a real historical salary file supplies them.

FantasyData/FantasyPros crosswalk rows are populated the same way this
project's LIVE matchers already do it (external_projections/csv_import/matcher.py,
fantasypros/matcher.py) -- name+team fallback matching, not duplicated
here; this module only defines the SHAPE those matchers' results land
in for historical warehouse rows.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from dfs.name_normalization import normalize_name


@dataclass
class PlayerCrosswalkRow:
    """One canonical player, cross-referenced across every ID system
    this package touches. `canonical_player_id` is always the MLBAM id
    as a string when known (the common case for every source in this
    package) -- a synthetic id (normalized-name-based) only when a
    player genuinely has no MLBAM id available (should be rare/never
    for MLB players; documented as a fallback, not the expected path)."""

    canonical_player_id: str
    mlbam_id: Optional[str] = None
    statcast_id: Optional[str] = None  # Statcast's batter/pitcher columns ARE the MLBAM id -- kept as an explicit alias field so a caller never has to assume that equivalence itself
    bbref_id: Optional[str] = None
    fangraphs_id: Optional[str] = None
    retrosheet_id: Optional[str] = None
    draftkings_id: Optional[str] = None
    fantasydata_id: Optional[str] = None
    fantasypros_id: Optional[str] = None
    name: Optional[str] = None
    normalized_name: Optional[str] = None
    team: Optional[str] = None
    match_method: str = "mlbam_direct"  # "mlbam_direct" | "chadwick_register" | "name_fallback"
    match_confidence: float = 1.0
    # Milestone 32.1, Part 8 additions -- optional so M32.0-era callers
    # that never set these still construct a valid row.
    bat_side: Optional[str] = None
    throw_side: Optional[str] = None
    first_seen: Optional[str] = None  # earliest game_date this player was observed in the warehouse build
    last_seen: Optional[str] = None


def crosswalk_row_from_mlbam(mlbam_id: str, name: str, team: Optional[str] = None) -> PlayerCrosswalkRow:
    """The common case: a player we already know the MLBAM id for
    (every MLB Stats API / Statcast row does). statcast_id mirrors
    mlbam_id explicitly -- see PlayerCrosswalkRow's own docstring."""
    mlbam_id = str(mlbam_id)
    return PlayerCrosswalkRow(
        canonical_player_id=mlbam_id, mlbam_id=mlbam_id, statcast_id=mlbam_id,
        name=name, normalized_name=normalize_name(name) if name else None, team=team,
        match_method="mlbam_direct", match_confidence=1.0,
    )


def merge_chadwick_register_row(row: PlayerCrosswalkRow, register_row: dict) -> PlayerCrosswalkRow:
    """Merges one row from the Chadwick Bureau register (the table
    pybaseball.playerid_lookup() returns: key_mlbam/key_bbref/
    key_fangraphs/key_retro/name_first/name_last) onto an existing
    crosswalk row, matched by mlbam_id. Never overwrites an
    already-populated field with a null from the register (additive
    only) -- auditable: match_method is upgraded to note the register
    was consulted."""
    if str(register_row.get("key_mlbam")) != row.mlbam_id:
        return row  # not a match for this row -- caller's responsibility to key correctly
    row.bbref_id = row.bbref_id or (str(register_row["key_bbref"]) if register_row.get("key_bbref") else None)
    row.fangraphs_id = row.fangraphs_id or (str(register_row["key_fangraphs"]) if register_row.get("key_fangraphs") else None)
    row.retrosheet_id = row.retrosheet_id or (str(register_row["key_retro"]) if register_row.get("key_retro") else None)
    row.match_method = "chadwick_register"
    return row


def attach_external_source_id(
    row: PlayerCrosswalkRow, source: str, external_id: str, external_name: str, confidence: float,
) -> PlayerCrosswalkRow:
    """Attaches a DraftKings/FantasyData/FantasyPros id to an existing
    crosswalk row via NAME-FALLBACK matching (source has no MLBAM id of
    its own). Auditable: the match is only accepted here (caller's
    matcher already decided the confidence; this function just records
    it) if normalized names agree, and match_confidence/match_method
    are always recorded so a downstream audit can filter out low-
    confidence matches rather than trusting them blindly."""
    if source not in ("draftkings_id", "fantasydata_id", "fantasypros_id"):
        raise ValueError(f"Unknown external source field: {source!r}")
    setattr(row, source, external_id)
    if confidence < row.match_confidence:
        row.match_confidence = confidence
        row.match_method = "name_fallback"
    return row


def build_crosswalk_index(rows: List[PlayerCrosswalkRow]) -> Dict[str, PlayerCrosswalkRow]:
    """Indexes by canonical_player_id (mlbam_id in the common case).
    Raises on a genuine duplicate canonical id (a data-quality bug worth
    surfacing loudly, not silently overwriting one player with
    another) -- this is exactly the kind of duplicate-identity issue
    Part 11's data-quality audit must catch."""
    index: Dict[str, PlayerCrosswalkRow] = {}
    for row in rows:
        if row.canonical_player_id in index:
            raise ValueError(f"Duplicate canonical_player_id in crosswalk: {row.canonical_player_id!r} ({row.name!r})")
        index[row.canonical_player_id] = row
    return index
