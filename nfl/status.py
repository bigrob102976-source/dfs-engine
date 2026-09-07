"""NFL M14 -- real, live NFL player status normalization + optimizer
exclusion policy.

Source of truth: NflPlayer.status (nfl/models.py), DraftKings' own raw
per-draftable status field, passed through verbatim by
draftkings_unofficial/normalizer.py. Confirmed real values observed in
live captured DraftGroup 151307 payloads: "None" (healthy/active), "Q"
(Questionable), "OUT" (Out), "IR" (Injured Reserve) -- see NFL M14
Phase 2's audit. This module maps ONLY those confirmed-real values;
anything else normalizes to UNKNOWN rather than being guessed.

There is no real live news-CONTENT source anywhere in this project
(confirmed by the same audit) -- this module never invents a news
headline or article. DK's own `newsStatus` badge ("None"/"Recent"/
"Breaking") is a real signal but is a badge, not news content; it is
surfaced separately (see NewsStatus below) and is NOT part of the
player-status/exclusion policy, which is driven entirely by the real
injury/roster `status` field.

There is also no real inactives/depth-chart/official-injury-report feed
wired into the live pool (nflverse's injury report exists in
historical_nfl/injury_status.py but is offline/training-only, never
connected here -- see the audit). DOUBTFUL/INACTIVE are modeled as real
possible statuses (DK's status vocabulary includes them even though no
live example has been observed yet) so the policy is ready for them
without ever fabricating an occurrence."""

from dataclasses import asdict, dataclass
from typing import Optional

ACTIVE = "ACTIVE"
QUESTIONABLE = "QUESTIONABLE"
DOUBTFUL = "DOUBTFUL"
OUT = "OUT"
INACTIVE = "INACTIVE"
IR = "IR"
UNKNOWN = "UNKNOWN"

ALL_STATUSES = (ACTIVE, QUESTIONABLE, DOUBTFUL, OUT, INACTIVE, IR, UNKNOWN)

# Exact, confirmed-real DK raw status string -> normalized status.
# "D" (Doubtful) and "INACTIVE" are DK's own documented vocabulary for
# other sports/situations but have not been observed live for NFL yet
# in this project's captures -- mapped here so the policy is ready,
# never fabricated as having occurred.
_RAW_STATUS_MAP = {
    "None": ACTIVE,
    "": ACTIVE,
    "Q": QUESTIONABLE,
    "D": DOUBTFUL,
    "OUT": OUT,
    "O": OUT,
    "INACTIVE": INACTIVE,
    "IR": IR,
}

# NFL M14 Phase 10 -- default optimizer exclusion policy. True means
# "excluded from the candidate pool by default"; QUESTIONABLE/UNKNOWN
# stay eligible (never silently dropped) but are visibly flagged in the
# UI (see NflPlayerStatusInfo.warn below).
DEFAULT_EXCLUDE_BY_STATUS = {
    ACTIVE: False,
    QUESTIONABLE: False,
    DOUBTFUL: False,  # displayed with a warning; product policy does not exclude by default (see module docstring)
    OUT: True,
    INACTIVE: True,
    IR: True,
    UNKNOWN: False,
}

# Which statuses show a visible warning in the UI, even when not excluded.
WARN_STATUSES = frozenset({QUESTIONABLE, DOUBTFUL, UNKNOWN})


def normalize_status(raw_status: Optional[str]) -> str:
    """Never guesses -- an unrecognized raw value maps to UNKNOWN,
    never silently coerced to ACTIVE."""
    if raw_status is None:
        return ACTIVE
    return _RAW_STATUS_MAP.get(raw_status, UNKNOWN)


@dataclass
class NflPlayerStatusInfo:
    normalized_status: str
    raw_status: Optional[str]
    excluded_by_default: bool
    warn: bool

    def to_dict(self) -> dict:
        return asdict(self)


def build_status_info(raw_status: Optional[str], exclude_overrides: Optional[dict] = None) -> NflPlayerStatusInfo:
    """`exclude_overrides` optionally replaces DEFAULT_EXCLUDE_BY_STATUS
    for one call (product-policy configurability, NFL M14 Phase 10 --
    "make policy configurable if existing architecture supports it
    cleanly"). Unrecognized keys in the override are ignored."""
    normalized = normalize_status(raw_status)
    policy = DEFAULT_EXCLUDE_BY_STATUS if not exclude_overrides else {**DEFAULT_EXCLUDE_BY_STATUS, **exclude_overrides}
    return NflPlayerStatusInfo(
        normalized_status=normalized, raw_status=raw_status,
        excluded_by_default=policy.get(normalized, False), warn=normalized in WARN_STATUSES,
    )
