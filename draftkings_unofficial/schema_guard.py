"""Milestone 31.2 -- basic schema-change detection for the unofficial
DraftKings endpoints.

This is an undocumented interface; DraftKings can change a response
shape at any time. Rather than letting a normalizer crash on a missing
field (KeyError) or silently produce empty/wrong records, every
normalizer entry point checks the raw payload against a small set of
EXPECTED top-level keys first. A mismatch returns a SchemaCheckResult
with `ok=False` instead of raising -- callers (normalizer.py) use this
to skip normalizing that payload and report SCHEMA_CHANGED rather than
crash the whole collection run.

Deliberately minimal: this checks for the PRESENCE of the keys this
client's normalizers actually read, not a full JSON-schema validation
-- DraftKings adding NEW fields is normal and expected (never flagged);
only a genuinely required key going missing is a schema change worth
surfacing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

# The keys each endpoint's normalizer actually depends on. Kept in one
# place so the "if required fields disappear" check has a single
# source of truth per endpoint.
EXPECTED_KEYS = {
    "sports": ["sports"],
    "contests": ["Contests", "DraftGroups", "GameTypes"],
    "draftables": ["draftables", "competitions"],
    "game_type_rules": ["gameTypeId", "lineupTemplate", "salaryCap"],
    "contest_details": ["contestDetail"],
}

EXPECTED_SPORT_KEYS = ["sportId", "regionAbbreviatedSportName", "fullName", "hasPublicContests", "isEnabled"]
EXPECTED_CONTEST_KEYS = ["id", "n", "s", "dg", "gameType", "gameTypeId", "sd"]
EXPECTED_DRAFT_GROUP_KEYS = ["DraftGroupId", "SportId", "GameTypeId", "StartDate"]
EXPECTED_DRAFTABLE_KEYS = ["draftableId", "displayName", "position", "salary", "teamId"]
EXPECTED_COMPETITION_KEYS = ["competitionId", "startTime"]


@dataclass
class SchemaCheckResult:
    ok: bool
    endpoint: str
    missing_keys: List[str] = field(default_factory=list)
    observed_keys: List[str] = field(default_factory=list)
    sample: Any = None
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "status": "ok" if self.ok else "SCHEMA_CHANGED",
            "endpoint": self.endpoint,
            "missing_keys": self.missing_keys,
            "observed_keys": self.observed_keys,
            "sample": self.sample,
            "checked_at": self.checked_at,
        }


def _sample(payload: Any, max_len: int = 500) -> Any:
    """A small, sanitized preview of the payload for the schema-change
    report -- never the full raw response (could be large), never any
    credential-shaped field (this client never receives/stores one, so
    there's nothing to redact, but the size cap alone keeps reports
    readable)."""
    try:
        text = str(payload)
    except Exception:
        return None
    return text[:max_len]


def check(endpoint: str, payload: Any, required_keys: List[str]) -> SchemaCheckResult:
    if not isinstance(payload, dict):
        return SchemaCheckResult(ok=False, endpoint=endpoint, missing_keys=list(required_keys), observed_keys=[], sample=_sample(payload))
    observed = list(payload.keys())
    missing = [k for k in required_keys if k not in payload]
    return SchemaCheckResult(ok=not missing, endpoint=endpoint, missing_keys=missing, observed_keys=observed, sample=_sample(payload) if missing else None)


def check_sports(payload: Any) -> SchemaCheckResult:
    return check("sports", payload, EXPECTED_KEYS["sports"])


def check_contests(payload: Any) -> SchemaCheckResult:
    return check("contests", payload, EXPECTED_KEYS["contests"])


def check_draftables(payload: Any) -> SchemaCheckResult:
    return check("draftables", payload, EXPECTED_KEYS["draftables"])


def check_game_type_rules(payload: Any) -> SchemaCheckResult:
    return check("game_type_rules", payload, EXPECTED_KEYS["game_type_rules"])


def check_contest_details(payload: Any) -> SchemaCheckResult:
    return check("contest_details", payload, EXPECTED_KEYS["contest_details"])


def check_record(endpoint: str, record: Dict[str, Any], required_keys: List[str]) -> SchemaCheckResult:
    """Per-RECORD check (one sport/contest/draft group/draftable/
    competition dict), distinct from the top-level `check()` above --
    used when the top-level shape is fine but individual records within
    a list are missing fields the normalizer needs."""
    return check(endpoint, record, required_keys)
