"""NFL M14 -- the canonical saved-lineup record for the late-swap /
game-day workflow. Deliberately separate from nfl/optimizer_models.py's
NflLineup: that dataclass represents ONE FRESH SOLVE's output (built,
scored, and discarded or displayed in the same request); this
represents a USER-OWNED, PERSISTED, MUTABLE record that outlives any
single optimizer run and gets read back days later for late swap (see
dashboard/lib/db/nflSavedLineups.ts for the persistence layer, and
nfl/late_swap.py for how this gets updated in place).

Every field snapshot here (projection_snapshot/ownership_snapshot) is
frozen at SAVE time and never silently overwritten -- late swap may
show "Original vs Current" by re-fetching fresh data alongside this
snapshot, but this module itself never mutates a snapshot value, only
the slot list as a whole (see NflSavedLineup.replace_slots())."""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

SPORT_NFL = "NFL"
SITE_DRAFTKINGS = "DraftKings"

_SLOT_FIELD_NAMES = (
    "roster_slot", "draftkings_player_id", "name", "team", "opponent", "game_id", "game_start_utc",
    "position", "salary", "projection_snapshot", "ceiling_snapshot", "ownership_snapshot",
)


class SavedLineupCorruptionError(ValueError):
    """A saved lineup's own stored data is structurally invalid (e.g.
    a duplicate player, a slot referencing an unknown label) -- raised
    before any late-swap solve is attempted, never silently tolerated."""


@dataclass
class NflSavedLineupSlot:
    roster_slot: str  # "QB" | "RB1" | "RB2" | "WR1" | "WR2" | "WR3" | "TE" | "FLEX" | "DST"
    draftkings_player_id: str
    name: str
    team: str
    opponent: Optional[str]
    game_id: str
    game_start_utc: str  # real ISO-8601 UTC, snapshotted at save time -- see nfl/game_lock.py::parse_game_start_utc
    position: str
    salary: int
    projection_snapshot: Optional[float] = None
    ceiling_snapshot: Optional[float] = None
    ownership_snapshot: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "NflSavedLineupSlot":
        missing = [f for f in ("roster_slot", "draftkings_player_id", "name", "team", "game_id", "game_start_utc", "position", "salary") if f not in d]
        if missing:
            raise SavedLineupCorruptionError(f"Saved lineup slot is missing required field(s): {missing}.")
        return NflSavedLineupSlot(**{k: d.get(k) for k in _SLOT_FIELD_NAMES})


@dataclass
class NflSavedLineup:
    lineup_id: str
    sport: str
    site: str
    draft_group_id: int
    slate_date: str
    created_at: str
    updated_at: str
    mode: str
    stack_config: dict
    slots: List[NflSavedLineupSlot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lineup_id": self.lineup_id, "sport": self.sport, "site": self.site,
            "draft_group_id": self.draft_group_id, "slate_date": self.slate_date,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "mode": self.mode, "stack_config": self.stack_config,
            "slots": [s.to_dict() for s in self.slots],
        }

    def player_keys(self) -> List[str]:
        return [s.draftkings_player_id for s in self.slots]

    def replace_slots(self, new_slots: List[NflSavedLineupSlot]) -> "NflSavedLineup":
        """Returns a NEW NflSavedLineup with slots replaced -- the
        caller (nfl/late_swap.py) is responsible for persisting it via
        dashboard/lib/db/nflSavedLineups.ts::updateSavedLineupSlots();
        this module never touches storage itself."""
        return NflSavedLineup(
            lineup_id=self.lineup_id, sport=self.sport, site=self.site, draft_group_id=self.draft_group_id,
            slate_date=self.slate_date, created_at=self.created_at, updated_at=self.updated_at,
            mode=self.mode, stack_config=self.stack_config, slots=new_slots,
        )

    @staticmethod
    def from_dict(d: dict) -> "NflSavedLineup":
        slots = [NflSavedLineupSlot.from_dict(s) for s in d.get("slots", [])]
        return NflSavedLineup(
            lineup_id=d["lineup_id"], sport=d.get("sport", SPORT_NFL), site=d.get("site", SITE_DRAFTKINGS),
            draft_group_id=d["draft_group_id"], slate_date=d["slate_date"],
            created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
            mode=d.get("mode", "roster_feasibility"), stack_config=d.get("stack_config", {}), slots=slots,
        )


def validate_saved_lineup(lineup: NflSavedLineup) -> None:
    """Raises SavedLineupCorruptionError for structural problems that
    would make a late-swap solve meaningless or dangerous to run.
    Independent of any DB/API-layer validation -- this module never
    trusts its caller."""
    keys = lineup.player_keys()
    if len(set(keys)) != len(keys):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise SavedLineupCorruptionError(f"Saved lineup contains duplicate player ID(s): {dupes}.")

    seen_slots: Dict[str, int] = {}
    for slot in lineup.slots:
        seen_slots[slot.roster_slot] = seen_slots.get(slot.roster_slot, 0) + 1
    dupe_slots = [label for label, count in seen_slots.items() if count > 1]
    if dupe_slots:
        raise SavedLineupCorruptionError(f"Saved lineup has more than one player in slot(s): {dupe_slots}.")
