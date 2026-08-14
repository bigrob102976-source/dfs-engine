"""Matches imported CSV rows against our own canonical MLB player
identity by REUSING dfs/player_resolver.py verbatim -- the exact same
tiered (crosswalk -> name+team exact -> ambiguous -> name-only-unique
fallback -> unmatched) logic already proven against DraftKings salary
CSVs. Nothing here re-implements or loosens that matching; a CSV row is
simply adapted into the same DKSalaryRow shape the resolver already
expects.

This matching is informational only: it powers the import wizard's
Matched/Unmatched/Ambiguous/Needs-Review validation summary. It never
determines what gets written into the immutable baseline snapshot (see
importer.py) -- the LATER, separate identity match that actually feeds
the optimizer/adjustment pipeline happens in
external_projections/projection_merge.py, unchanged, when
scripts/run_projection_adjustment.py runs against the saved snapshot.

Deliberately reads the Research Package with pitcher_input/batter_input's
own `load_research_package` (read-only, raises if missing) rather than
dfs/pool_builder.py's `ensure_research_package` (which auto-BUILDS a
missing package, including a live MLB Stats API call) -- a CSV import
preview can be re-run on every mapping edit, so it must never have a
network-touching side effect. If no package exists yet for the date, a
CSV can still be analyzed/saved; it simply won't have anything to match against.
"""

from typing import Dict, List

from dfs.models import DKSalaryRow, PlayerMatch
from dfs.player_resolver import build_canonical_by_id, build_canonical_index, build_name_only_index, resolve_player
from research.adapters import batter_input, pitcher_input


def _load_package(research_output_root: str, date: str) -> dict:
    pitcher_pkg = pitcher_input.load_research_package(research_output_root, date)
    batter_pkg = batter_input.load_research_package(research_output_root, date)
    return {
        "games": pitcher_pkg["games"], "teams": pitcher_pkg["teams"],
        "pitchers": pitcher_pkg["pitchers"], "batters": batter_pkg["batters"],
    }


def _to_dk_row(index: int, row: Dict[str, object]) -> DKSalaryRow:
    position = row.get("position")
    return DKSalaryRow(
        dk_player_id=str(row.get("player_id") or f"csv-row-{index}"),
        name=str(row.get("name") or ""),
        team_abbrev=str(row.get("team") or ""),
        dk_positions=[position] if position else [],
        salary=0,  # not used by resolve_player; a real salary is never invented here
        game_info="",
    )


def match_rows(normalized_rows: List[Dict[str, object]], research_output_root: str, date: str) -> List[PlayerMatch]:
    """`normalized_rows` are the output of mapping.apply_mapping. Rows
    missing a name are skipped entirely (nothing to match) -- they are
    still counted separately by validation.py."""
    package = _load_package(research_output_root, date)
    index = build_canonical_index(package)
    name_only_index = build_name_only_index(index)
    canonical_by_id = build_canonical_by_id(index)

    matches: List[PlayerMatch] = []
    for i, row in enumerate(normalized_rows):
        if not row.get("name"):
            continue
        dk_row = _to_dk_row(i, row)
        matches.append(resolve_player(dk_row, index, name_only_index, canonical_by_id=canonical_by_id))
    return matches


def known_team_abbreviations(research_output_root: str, date: str) -> set:
    package = _load_package(research_output_root, date)
    return {t["abbreviation"] for t in package.get("teams", []) if t.get("abbreviation")}
