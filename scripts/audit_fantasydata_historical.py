"""Milestone 31.0 -- FantasyData/SportsDataIO historical access audit.

Calls exactly THREE live endpoints (one each: historical projections,
historical actual results, historical DFS slates) for one fixed test
date, saves the raw responses as immutable artifacts, and prints a
sanitized data-quality report to stdout. Never prints, logs, or saves
the API key.

This script is READ-ONLY with respect to the rest of the codebase: it
does not touch Native, AI, FantasyPros, Vegas, Ownership, Optimizer,
Stripe, membership, or auth, and it does not train or tune anything.

Per the milestone's explicit "do not make additional API calls beyond
what is reasonably necessary" instruction, this script makes exactly
one call per endpoint and must not be run in a retry loop.

    python scripts/audit_fantasydata_historical.py --date 2025-JUN-15
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantasydata_audit import client  # noqa: E402
from fantasydata_audit.client import (  # noqa: E402
    FantasyDataAuthenticationError,
    FantasyDataNotConfiguredError,
    FantasyDataRateLimitedError,
    FantasyDataUnavailableError,
)

AUDIT_OUTPUT_ROOT = Path("data/fantasydata/audit")


def _save_raw(save_dir: Path, filename: str, data: Any) -> Optional[str]:
    if data is None:
        return None
    save_dir.mkdir(parents=True, exist_ok=True)
    path = save_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return str(path)


def _field_names(records: List[dict]) -> List[str]:
    names: List[str] = []
    seen = set()
    for r in records:
        if not isinstance(r, dict):
            continue
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                names.append(k)
    return names


def _null_fraction(records: List[dict], field: str) -> Optional[float]:
    if not records:
        return None
    n_null = sum(1 for r in records if isinstance(r, dict) and (r.get(field) is None or r.get(field) == ""))
    return round(n_null / len(records), 3)


def _duplicate_player_ids(records: List[dict]) -> int:
    ids = [r.get("PlayerID") for r in records if isinstance(r, dict) and r.get("PlayerID") is not None]
    counts = Counter(ids)
    return sum(1 for _, c in counts.items() if c > 1)


def _print_section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _report_list_endpoint(label: str, result: Optional[dict], error: Optional[Exception]) -> Optional[List[dict]]:
    _print_section(label)
    if error is not None:
        print(f"ERROR: {type(error).__name__}: {error}")
        return None
    status = result["status"]
    data = result["data"]
    print(f"HTTP status: {status}")
    record_type = type(data).__name__
    print(f"Response type: {record_type}")
    records = data if isinstance(data, list) else []
    if not isinstance(data, list):
        print("Response is NOT a list -- treating as zero records for this audit's record-count purposes.")
        print(f"Raw (non-list) payload preview: {json.dumps(data)[:500]}")
    print(f"Number of records: {len(records)}")
    if records:
        print("First 2 records:")
        print(json.dumps(records[:2], indent=2, default=str))
        print(f"Available field names: {_field_names(records)}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit FantasyData/SportsDataIO MLB historical API access.")
    parser.add_argument("--date", required=True, help="Date string exactly as the API endpoint expects, e.g. 2025-JUN-15")
    parser.add_argument("--save-date", default=None, help="ISO date (YYYY-MM-DD) subdirectory name for saved artifacts; defaults to --date as given")
    args = parser.parse_args()

    if not client.is_configured():
        print(json.dumps({"status": "not_configured", "detail": "FANTASYDATA_API_KEY is not set."}))
        return

    save_dir = AUDIT_OUTPUT_ROOT / (args.save_date or args.date)

    # ---- TEST 1: historical projections (exactly one call) ----
    projections_result = None
    projections_error = None
    try:
        projections_result = client.get_player_game_projection_stats_by_date(args.date)
    except (FantasyDataNotConfiguredError, FantasyDataAuthenticationError, FantasyDataRateLimitedError, FantasyDataUnavailableError) as exc:
        projections_error = exc
    projections_records = _report_list_endpoint("TEST 1 -- HISTORICAL PROJECTIONS", projections_result, projections_error)
    projections_path = None
    if projections_result is not None:
        projections_path = _save_raw(save_dir, "projections.json", projections_result["data"])
        print(f"Saved: {projections_path}")

    # ---- TEST 2: historical actual results (exactly one call) ----
    actual_result = None
    actual_error = None
    try:
        actual_result = client.get_fantasy_game_stats_by_date(args.date)
    except (FantasyDataNotConfiguredError, FantasyDataAuthenticationError, FantasyDataRateLimitedError, FantasyDataUnavailableError) as exc:
        actual_error = exc
    actual_records = _report_list_endpoint("TEST 2 -- HISTORICAL ACTUAL RESULTS", actual_result, actual_error)
    actual_path = None
    if actual_result is not None:
        actual_path = _save_raw(save_dir, "actual_results.json", actual_result["data"])
        print(f"Saved: {actual_path}")

    # ---- TEST 3: historical DFS slates (exactly one call) ----
    slates_result = None
    slates_error = None
    try:
        slates_result = client.get_dfs_slates_by_date(args.date)
    except (FantasyDataNotConfiguredError, FantasyDataAuthenticationError, FantasyDataRateLimitedError, FantasyDataUnavailableError) as exc:
        slates_error = exc
    _print_section("TEST 3 -- HISTORICAL DFS SLATES")
    slates_records: List[dict] = []
    slates_path = None
    if slates_error is not None:
        print(f"ERROR: {type(slates_error).__name__}: {slates_error}")
    elif slates_result is not None:
        status = slates_result["status"]
        data = slates_result["data"]
        print(f"HTTP status: {status}")
        print(f"Response type: {type(data).__name__}")
        slates_records = data if isinstance(data, list) else []
        print(f"Number of slates: {len(slates_records)}")
        slate_ids = [s.get("SlateID") for s in slates_records if isinstance(s, dict)]
        print(f"Slate IDs: {slate_ids}")
        operators = sorted({s.get("Operator") for s in slates_records if isinstance(s, dict) and s.get("Operator")})
        print(f"Operators represented: {operators}")
        dk_slates = [s for s in slates_records if isinstance(s, dict) and s.get("Operator") == "DraftKings"]
        print(f"DraftKings represented: {bool(dk_slates)}")
        for s in dk_slates:
            players = s.get("DfsSlatePlayers") or []
            print(f"  DK slate: id={s.get('SlateID')} name={s.get('OperatorName')} type={s.get('SlateType') or s.get('OperatorGameType')} players={len(players)}")
            if players:
                p0 = players[0]
                print(f"    Sample DFS slate player fields: {sorted(p0.keys())}")
                print(f"    OperatorSalary populated: {p0.get('OperatorSalary') is not None}")
                print(f"    OperatorPlayerID present: {'OperatorPlayerID' in p0}")
                print(f"    PlayerID present: {'PlayerID' in p0}")
                positions = sorted({pp.get("OperatorPosition") for pp in players if isinstance(pp, dict) and pp.get("OperatorPosition")})
                print(f"    Positions: {positions}")
                teams = sorted({pp.get("Team") for pp in players if isinstance(pp, dict) and pp.get("Team")})
                print(f"    Teams: {teams}")
        slates_path = _save_raw(save_dir, "dfs_slates.json", data)
        print(f"Saved: {slates_path}")

    # ---- Data-quality sanity checks ----
    _print_section("DATA-QUALITY SANITY CHECKS")
    for label, records in (("Projections", projections_records or []), ("Actual results", actual_records or [])):
        if not records:
            print(f"{label}: no records to check.")
            continue
        print(f"{label}:")
        print(f"  PlayerID present: {'PlayerID' in records[0]}")
        print(f"  GameID present: {'GameID' in records[0]}")
        print(f"  FantasyPointsDraftKings present: {'FantasyPointsDraftKings' in records[0]}")
        print(f"  DraftKingsSalary present: {'DraftKingsSalary' in records[0]}")
        print(f"  Null fraction PlayerID: {_null_fraction(records, 'PlayerID')}")
        print(f"  Null fraction FantasyPointsDraftKings: {_null_fraction(records, 'FantasyPointsDraftKings')}")
        print(f"  Duplicate PlayerIDs: {_duplicate_player_ids(records)}")
        batting_fields = [f for f in ("Hits", "HomeRuns", "RBI", "Runs", "Walks", "StolenBases", "AtBats") if f in records[0]]
        pitching_fields = [f for f in ("InningsPitchedDecimal", "Strikeouts", "Wins", "Losses", "Saves", "EarnedRuns", "PitchingHits") if f in records[0]]
        print(f"  Batting fields present: {batting_fields}")
        print(f"  Pitching fields present: {pitching_fields}")
        status_fields = [f for f in ("InjuryStatus", "InjuryBodyPart", "InjuryStartDate", "InjuryNotes") if f in records[0]]
        print(f"  Injury/status fields present: {status_fields}")

    print("\nDone. Review the sections above and the saved raw files for the audit report.")


if __name__ == "__main__":
    main()
