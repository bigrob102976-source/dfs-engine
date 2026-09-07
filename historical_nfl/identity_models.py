"""NFL M6B -- the durable DraftKings <-> GSIS identity crosswalk model.

canonical_player_id strategy (Phase 12): minted ONCE per DraftKings
player_id, NEVER changed afterward, even if a GSIS mapping is found or
corrected later:
  - "gsis:<gsis_id>"  when a GSIS match exists at the moment this row is
    first created (the common, eventual case for every real player).
  - "dk:<draftkings_player_id>" when no GSIS match exists yet (a genuine
    rookie/UDFA/free-agent-signing not yet reflected in nflverse's
    roster data -- see identity_matching.py's real Phase-9 findings).
  - "dst:<team_abbr>" for team defenses -- a team abbreviation is
    already a stable, durable identity; no synthetic player id is
    invented for it (Phase 4).

If a `dk:`-anchored row is later reviewed and approved with a real
gsis_id, the row's own `gsis_id` field is updated -- canonical_player_id
itself never is. This is the one thing every downstream system (a
future historical feature join, a saved projection, an ownership
model) is allowed to assume never moves under it.

match_confidence is a small set of FIXED values keyed to match_method
(never a fuzzy/edit-distance similarity score -- this project's
existing dfs/player_resolver.py precedent uses categorical tiers for
the same reason: a numeric "score" invites treating a near-miss as
good enough, which this milestone explicitly forbids)."""

from dataclasses import asdict, dataclass, field
from typing import List, Optional

# -- Match result states (Phase 7) -- every resolution attempt ends in
# exactly one of these; never silently dropped. --
STATUS_MATCHED = "MATCHED"
STATUS_UNMATCHED = "UNMATCHED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"

# -- Match methods (Phase 3 hierarchy, in preference order) --
METHOD_EXISTING_CROSSWALK = "existing_crosswalk"
METHOD_NAME_TEAM_EXACT = "name_team_exact"
METHOD_NAME_POSITION_CROSS_TEAM = "name_position_cross_team"
METHOD_EXCEPTION_TABLE = "exception_table"

# -- Fixed, deterministic confidence per method -- describes the tier
# reached, never used to DECIDE the match (the tier hierarchy alone
# decides; this is reporting/filtering metadata only). --
CONFIDENCE_BY_METHOD = {
    METHOD_EXISTING_CROSSWALK: 1.0,
    METHOD_NAME_TEAM_EXACT: 1.0,
    METHOD_NAME_POSITION_CROSS_TEAM: 0.9,
    METHOD_EXCEPTION_TABLE: 1.0,
}

# -- Crosswalk row review status (a persisted-row property, distinct
# from the per-attempt match `status` above) --
REVIEW_AUTO_APPROVED = "AUTO_APPROVED"
REVIEW_NEEDS_REVIEW = "NEEDS_REVIEW"
REVIEW_REVIEWED_APPROVED = "REVIEWED_APPROVED"
REVIEW_REVIEWED_REJECTED = "REVIEWED_REJECTED"

SOURCE_PROVENANCE = "NFLVERSE_DRAFTKINGS_CROSSWALK"


@dataclass
class NflIdentityMatchResult:
    """The ephemeral outcome of ONE identity-resolution attempt for one
    DraftKings player. Never persisted directly -- see NflCrosswalkRow
    for the durable row a MATCHED (or reviewed) result produces."""

    draftkings_player_id: str
    draftkings_draftable_id: Optional[str]
    dk_name: str
    dk_team: str
    dk_position: str
    status: str
    gsis_id: Optional[str] = None
    match_method: Optional[str] = None
    match_confidence: Optional[float] = None
    reason: Optional[str] = None
    candidate_gsis_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflCrosswalkRow:
    """One durable, reusable identity row -- persisted, looked up by
    draftkings_player_id on every future run (Tier 1) so a match is
    never redone from scratch once established."""

    canonical_player_id: str
    draftkings_player_id: Optional[str] = None
    gsis_id: Optional[str] = None
    is_team_entity: bool = False
    name: Optional[str] = None
    normalized_name: Optional[str] = None
    team: Optional[str] = None
    position: Optional[str] = None
    match_method: Optional[str] = None
    match_confidence: Optional[float] = None
    review_status: str = REVIEW_AUTO_APPROVED
    created_at: str = ""
    updated_at: str = ""
    source_provenance: str = SOURCE_PROVENANCE

    def to_dict(self) -> dict:
        return asdict(self)


class CrosswalkConflictError(Exception):
    """Raised when a newly resolved DK<->GSIS mapping disagrees with an
    existing APPROVED crosswalk row for the same draftkings_player_id --
    never silently overwritten (Phase 8)."""
