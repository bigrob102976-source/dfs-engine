"""Shared core for building a unified DFS player pool from a list of
DKSalaryRow-shaped rows, regardless of whether the rows came from a
parsed DraftKings CSV (dfs/draftkings_parser.py) or a normalized DFS
salary provider (dfs/providers/). Both scripts/build_dk_player_pool.py
and scripts/build_dfs_pool_from_provider.py call the functions here so
the matching/validation/persistence orchestration is never duplicated
between the two entry points -- only CLI argument parsing and console
printing stay separate.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dfs.lineup_smoke_test import find_one_legal_lineup
from dfs.models import DFSPlayer, DKSalaryRow
from dfs.persistence import save_match_report, save_player_pool
from dfs.player_pool import build_dfs_players, build_match_report
from dfs.player_resolver import build_canonical_by_id, build_canonical_index, build_name_only_index, resolve_all
from dfs.roster_feasibility import check_roster_feasibility
from dfs.slate_validation import validate_slate
from dfs.snapshot_selection import select_snapshot
from research.adapters import batter_input as batter_adapter
from research.adapters import pitcher_input as pitcher_adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError
from research.engine import build_research_package
from research.prediction_snapshot import timestamp_tag


def ensure_research_package(date: str, output_root: str) -> dict:
    try:
        pitcher_pkg = pitcher_adapter.load_research_package(output_root, date)
    except ResearchPackageNotFoundError:
        print(f"No research package found for {date} under {output_root}/ -- building it now...\n")
        report = build_research_package(date, output_root=output_root)
        print(f"Built: {report.games_found} games, {report.pitchers_found} pitchers, "
              f"{report.batters_found} batters, {len(report.warnings)} warnings.\n")
        pitcher_pkg = pitcher_adapter.load_research_package(output_root, date)

    batter_pkg = batter_adapter.load_research_package(output_root, date)
    return {"games": pitcher_pkg["games"], "teams": pitcher_pkg["teams"],
            "pitchers": pitcher_pkg["pitchers"], "batters": batter_pkg["batters"]}


def load_snapshot_arg(explicit_path, date, predictions_root, filename_prefix, label):
    snapshot, path = select_snapshot(explicit_path, date, predictions_root, filename_prefix)
    if snapshot is None:
        print(f"{label} snapshot: NONE FOUND for {date} under {predictions_root}/ "
              f"({label.lower()} projections will be unavailable)")
    else:
        source = "explicit" if explicit_path else "latest"
        print(f"{label} snapshot selected ({source}): {path}")
    return snapshot, path


class PoolBuildResult:
    """Bundles everything a CLI needs to print and persist -- avoids a
    long positional tuple return."""

    def __init__(self, players: List[DFSPlayer], report: dict, active_pool: List[DFSPlayer],
                 feasibility, legal_lineup, roster_feasibility_pass: bool,
                 pitcher_snapshot_path: Optional[str], batter_snapshot_path: Optional[str]):
        self.players = players
        self.report = report
        self.active_pool = active_pool
        self.feasibility = feasibility
        self.legal_lineup = legal_lineup
        self.roster_feasibility_pass = roster_feasibility_pass
        self.pitcher_snapshot_path = pitcher_snapshot_path
        self.batter_snapshot_path = batter_snapshot_path


def build_pool(
    dk_rows: List[DKSalaryRow], date: str, research_output_root: str, predictions_root: str,
    pitcher_snapshot_path: Optional[str] = None, batter_snapshot_path: Optional[str] = None,
    crosswalk: Optional[Dict[str, str]] = None,
) -> PoolBuildResult:
    """Runs identity matching, slate validation, player-pool assembly,
    and roster-feasibility checking -- identical to what
    scripts/build_dk_player_pool.py has always done, just factored out
    so a provider-sourced caller can reuse it verbatim."""
    package = ensure_research_package(date, research_output_root)
    pitcher_snapshot, pitcher_snapshot_path = load_snapshot_arg(
        pitcher_snapshot_path, date, predictions_root, "pitcher_board", "Pitcher")
    batter_snapshot, batter_snapshot_path = load_snapshot_arg(
        batter_snapshot_path, date, predictions_root, "batter_board", "Batter")

    canonical_index = build_canonical_index(package)
    canonical_by_id = build_canonical_by_id(canonical_index)
    matches = resolve_all(dk_rows, package, crosswalk or {})

    slate_validation = validate_slate(dk_rows, package)
    pitcher_raw_by_id = {str(r["player_id"]): r for r in package["pitchers"]}

    players = build_dfs_players(
        dk_rows, matches, canonical_by_id, slate_validation.dk_game_matches, pitcher_raw_by_id,
        pitcher_snapshot, batter_snapshot, pitcher_snapshot_path, batter_snapshot_path,
    )
    report = build_match_report(dk_rows, matches, players, slate_validation)

    active_pool = [p for p in players if p.lineup_status == "active"]
    feasibility = check_roster_feasibility(active_pool)
    legal_lineup = find_one_legal_lineup(active_pool) if feasibility.passed else None
    roster_feasibility_pass = feasibility.passed and legal_lineup is not None

    return PoolBuildResult(
        players=players, report=report, active_pool=active_pool, feasibility=feasibility,
        legal_lineup=legal_lineup, roster_feasibility_pass=roster_feasibility_pass,
        pitcher_snapshot_path=pitcher_snapshot_path, batter_snapshot_path=batter_snapshot_path,
    )


def save_pool(
    result: PoolBuildResult, date: str, dfs_input_root: str, extra_metadata: Optional[dict] = None,
    generated_at: Optional[str] = None,
) -> Tuple[Path, Path]:
    """Persists the pool + match report exactly like scripts/build_dk_player_pool.py
    always has (immutable, never overwritten). `extra_metadata` lets a
    caller record its own source (e.g. csv_source vs. provider_source).
    Pass `generated_at` explicitly when a caller also needs to save a raw
    source-file copy (e.g. the CSV) stamped with the exact SAME timestamp
    as this pool -- otherwise a fresh UTC timestamp is generated here."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    ts = timestamp_tag(generated_at)
    pool_metadata = {
        "slate_date": date,
        "generated_at_utc": generated_at,
        "pitcher_snapshot_path": result.pitcher_snapshot_path,
        "batter_snapshot_path": result.batter_snapshot_path,
        "roster_feasibility": result.feasibility.to_dict(),
        "roster_feasibility_pass": result.roster_feasibility_pass,
        **(extra_metadata or {}),
    }
    pool_path = save_player_pool(result.players, pool_metadata, date, ts, output_root=dfs_input_root)
    report_path = save_match_report(result.report, date, ts, output_root=dfs_input_root)
    return pool_path, report_path


def print_pool_report(result: PoolBuildResult) -> None:
    """The console report both scripts/build_dk_player_pool.py and
    scripts/build_dfs_pool_from_provider.py print -- identical either
    way, since a caller shouldn't be able to tell from the output alone
    whether the rows came from a CSV or a provider."""
    report = result.report
    print(f"DK entries: {report['dk_entries']}\n")
    print(f"Matched to MLB:\n{report['matched_to_mlb']} / {report['dk_entries']}\n")
    print(f"Pitchers matched:\n{report['pitchers_active']} / {report['pitchers_total']}\n")
    print(f"Starting hitters active:\n{report['hitters_active']}\n")
    print(f"DK hitters excluded because lineup not posted:\n{report['hitters_excluded_lineup_not_posted']}\n")
    print(f"Unmatched:\n{report['unmatched_count']}\n")
    print(f"Ambiguous:\n{report['ambiguous_count']}\n")
    print(f"Missing model projection:\n{report['missing_projection']}\n")
    print(f"Games on DK slate:\n{report['dk_games_total']}\n")
    print(f"Games matched to research:\n{report['dk_games_matched_to_research']} / {report['dk_games_total']}\n")
    print(f"Salary coverage:\n{report['salary_coverage_percent']}%\n")
    print(f"Position coverage:\n{report['position_coverage_percent']}%\n")

    if report["research_games_not_on_dk_slate"]:
        print(f"Research games EXCLUDED from this DK slate ({len(report['research_games_not_on_dk_slate'])}):")
        for g in report["research_games_not_on_dk_slate"]:
            print(f"  - game {g['game_id']}: {g['away_team_abbr']} @ {g['home_team_abbr']}")
        print()

    if report["unmatched"]:
        print(f"UNMATCHED ({len(report['unmatched'])}):")
        for m in report["unmatched"]:
            print(f"  - DK #{m['dk_player_id']} {m['dk_name']} ({m['dk_team']})")
        print()

    if report["ambiguous"]:
        print(f"AMBIGUOUS ({len(report['ambiguous'])}):")
        for m in report["ambiguous"]:
            print(f"  - DK #{m['dk_player_id']} {m['dk_name']} ({m['dk_team']}) "
                  f"-> candidates: {list(zip(m['candidate_mlb_ids'], m['candidate_names']))}")
        print()

    feasibility = result.feasibility
    print("Position counts (active pool):\n")
    print(f"P: {feasibility.position_counts.get('P', 0)}")
    for slot in ("C", "1B", "2B", "3B", "SS", "OF"):
        print(f"{slot}: {feasibility.position_counts.get(slot, 0)}")
    print()

    active_pool = result.active_pool
    salaries = [p.salary for p in active_pool] or [p.salary for p in result.players]
    print("Salary range\n")
    print(f"Lowest: {min(salaries) if salaries else 'n/a'}")
    print(f"Highest: {max(salaries) if salaries else 'n/a'}\n")

    projections = [p.projection for p in active_pool if p.projection is not None]
    print("Projection range\n")
    print(f"Lowest: {min(projections):.1f}" if projections else "Lowest: n/a")
    print(f"Highest: {max(projections):.1f}" if projections else "Highest: n/a")
    print()

    print("Roster feasibility:\n")
    print("PASS" if result.roster_feasibility_pass else "FAIL")
    if not feasibility.passed:
        for reason in feasibility.reasons:
            print(f"  - {reason}")
    elif result.legal_lineup is None:
        print("  - Position counts look sufficient, but no legal lineup was found under the salary cap "
              "(or the smoke-test search gave up early).")
    else:
        lineup_salary = sum(p.salary for p in result.legal_lineup)
        print(f"  - Example legal lineup found: {lineup_salary} salary used "
              f"({', '.join(p.name for p in result.legal_lineup)})")
    print()
