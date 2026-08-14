"""Deterministic column detection for an imported projection CSV
(Milestone 18). Matches each canonical field against a fixed synonym
table -- no fuzzy/edit-distance guessing, so a header either matches a
known synonym exactly (after case/whitespace/punctuation normalization)
or it doesn't, and the field is left for manual mapping. Never invents a
mapping the header doesn't support.
"""

import re
from typing import Dict, List, Optional

# Order matters for CANONICAL_FIELDS only in that it defines a stable
# iteration order for callers (e.g. building a preview table) -- it has
# no effect on detection itself.
CANONICAL_FIELDS: List[str] = [
    "name", "team", "opponent", "position", "salary",
    "projection", "ceiling", "floor", "ownership", "slate", "player_id",
]

# Each synonym is matched against the FULLY NORMALIZED header text
# (lowercase, punctuation stripped, whitespace collapsed) -- so "Own%",
# "own %", and "Own_Pct" all normalize to forms this table can list
# explicitly. New provider export formats should extend this table
# rather than relaxing the matching itself.
_SYNONYMS: Dict[str, List[str]] = {
    "name": ["player", "name", "player name", "playername"],
    "team": ["team", "tm", "teamabbrev", "team abbrev"],
    "opponent": ["opponent", "opp", "vs"],
    "position": ["position", "pos", "roster position"],
    "salary": ["salary", "sal"],
    "projection": ["projection", "proj", "fpts", "fantasy points", "points", "projected points"],
    "ceiling": ["ceiling", "ceil", "high"],
    "floor": ["floor", "low"],
    "ownership": ["ownership", "own", "own pct", "ownership pct", "ownership projection", "projected ownership"],
    "slate": ["slate", "slate name"],
    "player_id": ["player id", "playerid", "id", "provider player id", "player_id"],
}


def _normalize_header(header: str) -> str:
    text = (header or "").strip().lower()
    text = text.replace("%", " pct ")
    text = re.sub(r"[._\-]+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_columns(headers: List[str]) -> Dict[str, Optional[str]]:
    """Returns {canonical_field: original_header_or_None}. The FIRST
    header (in file order) matching a field's synonym list wins, so a
    duplicate/ambiguous header never silently overrides an earlier,
    already-detected column."""
    normalized_to_original: Dict[str, str] = {}
    for h in headers:
        norm = _normalize_header(h)
        if norm and norm not in normalized_to_original:
            normalized_to_original[norm] = h

    detected: Dict[str, Optional[str]] = {}
    for field in CANONICAL_FIELDS:
        match = None
        for synonym in _SYNONYMS[field]:
            if synonym in normalized_to_original:
                match = normalized_to_original[synonym]
                break
        detected[field] = match
    return detected
