"""Milestone 31.2 -- compares a parsed DraftKings salary-export CSV
(dfs/draftkings_parser.py's DKSalaryRow objects, the existing,
independent validation source) against this provider's normalized
DkDraftable list for the same slate.

Matching is tiered, mirroring dfs/player_resolver.py's own discipline
of preferring a real ID over a name-based guess:

  1. DK CSV's own numeric player ID vs. the API draftable's
     `player_dk_id` (both are DraftKings' own IDs -- when they agree,
     this is the strongest possible match, not a guess).
  2. Falls back to normalized (casefolded, whitespace-collapsed) name +
     team for anything not resolved by ID -- the two sources can
     legitimately use different ID spaces for the CSV vs. the
     Draftables API; this milestone's live audit (see
     scripts/audit_draftkings_unofficial.py) reports which tier
     actually did the work rather than assuming.

Never mutates either source; never "fixes" a mismatch -- this is a
report, not a reconciliation."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dfs.models import DKSalaryRow
from draftkings_unofficial.models import DkDraftable


def _normalize_name(name: str) -> str:
    return " ".join((name or "").split()).casefold()


@dataclass
class SalaryMismatch:
    name: str
    team: str
    csv_salary: int
    api_salary: Optional[int]


@dataclass
class PositionMismatch:
    name: str
    team: str
    csv_positions: List[str]
    api_position: Optional[str]


@dataclass
class GameMismatch:
    name: str
    team: str
    csv_game_info: str
    api_competition_id: Optional[int]


@dataclass
class CsvApiComparisonResult:
    api_rows: int
    csv_rows: int
    api_unique_players: int
    csv_unique_players: int
    matched_players: int
    matched_by_id: int
    matched_by_name_team: int
    api_only: List[str] = field(default_factory=list)
    csv_only: List[str] = field(default_factory=list)
    exact_salary_matches: int = 0
    salary_mismatches: List[SalaryMismatch] = field(default_factory=list)
    position_matches: int = 0
    position_mismatches: List[PositionMismatch] = field(default_factory=list)
    game_matches: int = 0
    game_mismatches: List[GameMismatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "api_rows": self.api_rows, "csv_rows": self.csv_rows,
            "api_unique_players": self.api_unique_players, "csv_unique_players": self.csv_unique_players,
            "matched_players": self.matched_players, "matched_by_id": self.matched_by_id,
            "matched_by_name_team": self.matched_by_name_team,
            "api_only": self.api_only, "csv_only": self.csv_only,
            "exact_salary_matches": self.exact_salary_matches,
            "salary_mismatches": [vars(m) for m in self.salary_mismatches],
            "position_matches": self.position_matches,
            "position_mismatches": [vars(m) for m in self.position_mismatches],
            "game_matches": self.game_matches,
            "game_mismatches": [vars(m) for m in self.game_mismatches],
        }


def compare_csv_to_api(csv_rows: List[DKSalaryRow], api_draftables: List[DkDraftable]) -> CsvApiComparisonResult:
    api_by_dk_id: Dict[str, DkDraftable] = {}
    api_by_name_team: Dict[str, DkDraftable] = {}
    for d in api_draftables:
        if d.player_dk_id is not None:
            api_by_dk_id.setdefault(str(d.player_dk_id), d)
        key = f"{_normalize_name(d.display_name)}|{(d.team_abbreviation or '').strip().upper()}"
        api_by_name_team.setdefault(key, d)

    matched_by_id = 0
    matched_by_name_team = 0
    csv_only: List[str] = []
    matched_pairs: List[tuple] = []

    for row in csv_rows:
        api_match = api_by_dk_id.get(row.dk_player_id)
        if api_match is not None:
            matched_by_id += 1
        else:
            key = f"{_normalize_name(row.name)}|{row.team_abbrev.strip().upper()}"
            api_match = api_by_name_team.get(key)
            if api_match is not None:
                matched_by_name_team += 1
        if api_match is None:
            csv_only.append(f"{row.name} ({row.team_abbrev})")
        else:
            matched_pairs.append((row, api_match))

    matched_api_draftable_ids = {api.draftable_id for _, api in matched_pairs}
    api_only = [f"{d.display_name} ({d.team_abbreviation})" for d in api_draftables if d.draftable_id not in matched_api_draftable_ids]

    exact_salary_matches = 0
    salary_mismatches: List[SalaryMismatch] = []
    position_matches = 0
    position_mismatches: List[PositionMismatch] = []
    game_matches = 0
    game_mismatches: List[GameMismatch] = []

    for row, api in matched_pairs:
        if row.salary == api.salary:
            exact_salary_matches += 1
        else:
            salary_mismatches.append(SalaryMismatch(name=row.name, team=row.team_abbrev, csv_salary=row.salary, api_salary=api.salary))

        # The Draftables API can itself report a multi-position player as
        # one slash-joined string (e.g. "2B/3B"), the same way the CSV's
        # own Position/Roster Position column does (see
        # dfs/draftkings_parser.py's identical split) -- split both sides
        # the same way rather than checking the whole unsplit API string
        # for membership in the CSV's already-split list, which would
        # falsely flag every real multi-position player as a mismatch.
        api_positions = {p.strip() for p in (api.position or "").split("/") if p.strip()}
        csv_positions = {p.strip() for p in row.dk_positions}
        if api_positions and api_positions & csv_positions:
            position_matches += 1
        else:
            position_mismatches.append(PositionMismatch(name=row.name, team=row.team_abbrev, csv_positions=list(row.dk_positions), api_position=api.position))

        # Game matching is necessarily approximate: the CSV's own
        # "Game Info" string and the API's numeric competition_id are
        # different representations of the same thing -- team presence
        # in the CSV's Game Info string is the only cross-checkable
        # signal available without a second, separate team/game lookup.
        team_in_game_info = row.team_abbrev.upper() in (row.game_info or "").upper()
        if team_in_game_info and api.competition_id is not None:
            game_matches += 1
        else:
            game_mismatches.append(GameMismatch(name=row.name, team=row.team_abbrev, csv_game_info=row.game_info, api_competition_id=api.competition_id))

    return CsvApiComparisonResult(
        api_rows=len(api_draftables), csv_rows=len(csv_rows),
        api_unique_players=len({d.player_dk_id or d.draftable_id for d in api_draftables}),
        csv_unique_players=len({row.dk_player_id for row in csv_rows}),
        matched_players=len(matched_pairs), matched_by_id=matched_by_id, matched_by_name_team=matched_by_name_team,
        api_only=api_only, csv_only=csv_only,
        exact_salary_matches=exact_salary_matches, salary_mismatches=salary_mismatches,
        position_matches=position_matches, position_mismatches=position_mismatches,
        game_matches=game_matches, game_mismatches=game_mismatches,
    )
