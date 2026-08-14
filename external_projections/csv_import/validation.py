"""Builds the import wizard's Validation Summary (Milestone 18): the
Players Imported / Matched / Unmatched / Duplicate / Missing Salary /
Missing Projection / Missing Position / Unknown Teams / Unknown
Opponents counts, plus a Needs Review list for ambiguous matches.
Pure aggregation over already-computed rows/matches -- never re-derives
or second-guesses matcher.py's decisions.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from dfs.models import PlayerMatch
from dfs.name_normalization import normalize_name
from dfs.team_abbreviations import normalize_dk_team_abbr


@dataclass
class NeedsReviewRow:
    row_index: int
    name: str
    team: str
    candidate_names: List[str]
    candidate_mlb_ids: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ImportValidationSummary:
    players_imported: int
    matched: int
    unmatched: int
    ambiguous: int
    duplicate_players: int
    missing_salary: int
    missing_projection: int
    missing_position: int
    unknown_teams: List[str] = field(default_factory=list)
    unknown_opponents: List[str] = field(default_factory=list)
    needs_review: List[NeedsReviewRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["needs_review"] = [r.to_dict() for r in self.needs_review]
        return d


def build_validation_summary(
    normalized_rows: List[Dict[str, object]],
    matches: List[PlayerMatch],
    known_team_abbrs: Optional[set] = None,
) -> ImportValidationSummary:
    known_team_abbrs = known_team_abbrs or set()
    named_rows = [r for r in normalized_rows if r.get("name")]

    seen_keys: Dict[str, int] = {}
    duplicate_players = 0
    for r in named_rows:
        key = f"{normalize_name(str(r.get('name')))}|{(r.get('team') or '')}"
        seen_keys[key] = seen_keys.get(key, 0) + 1
    duplicate_players = sum(1 for count in seen_keys.values() if count > 1)

    missing_salary = sum(1 for r in named_rows if r.get("salary") is None)
    missing_projection = sum(1 for r in named_rows if r.get("projection") is None)
    missing_position = sum(1 for r in named_rows if r.get("position") is None)

    unknown_teams = sorted({
        str(r["team"]) for r in named_rows
        if r.get("team") and normalize_dk_team_abbr(str(r["team"])) not in known_team_abbrs
    })
    unknown_opponents = sorted({
        str(r["opponent"]) for r in named_rows
        if r.get("opponent") and normalize_dk_team_abbr(str(r["opponent"])) not in known_team_abbrs
    })

    matched = sum(1 for m in matches if m.match_status == "matched")
    unmatched = sum(1 for m in matches if m.match_status == "unmatched")
    ambiguous_matches = [m for m in matches if m.match_status == "ambiguous"]

    needs_review = [
        NeedsReviewRow(
            row_index=i, name=m.dk_name, team=m.dk_team,
            candidate_names=m.candidate_names, candidate_mlb_ids=m.candidate_mlb_ids,
        )
        for i, m in enumerate(ambiguous_matches)
    ]

    return ImportValidationSummary(
        players_imported=len(named_rows),
        matched=matched,
        unmatched=unmatched,
        ambiguous=len(ambiguous_matches),
        duplicate_players=duplicate_players,
        missing_salary=missing_salary,
        missing_projection=missing_projection,
        missing_position=missing_position,
        unknown_teams=unknown_teams,
        unknown_opponents=unknown_opponents,
        needs_review=needs_review,
    )
