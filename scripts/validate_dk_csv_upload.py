"""CLI entry point: PREVIEW-ONLY structural validation of a real
DraftKings CSV, before the admin has decided to import it (BREAK-GLASS
ADMIN CSV UPLOAD, Phase 2's "Validate" step). Never saves anything --
distinct from scripts/upload_draftkings_csv.py, which persists. Reuses
dfs/draftkings_parser.py::parse_salary_csv verbatim (the same real-CSV
format check every other DK CSV path in this project uses) rather than
a second parser.

Duplicate-DK-player-ID detection lives here, not in the shared parser:
a real DraftKings Classic salary export has exactly one row per player,
so a duplicate ID is an admin-CSV-import-specific anomaly worth
flagging in the preview, not a general CSV-structure rule the parser
itself should enforce.

    python scripts/validate_dk_csv_upload.py --csv-path FILE
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.draftkings_parser import DraftKingsCSVFormatError, parse_salary_csv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview-only structural validation of a real DraftKings CSV.")
    parser.add_argument("--csv-path", required=True)
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(json.dumps({"status": "invalid", "reason": f"CSV file not found: {csv_path}"}))
        return

    try:
        dk_rows = parse_salary_csv(csv_path)
    except DraftKingsCSVFormatError as e:
        print(json.dumps({"status": "invalid", "reason": str(e)}))
        return
    except (UnicodeDecodeError, csv.Error):
        # Not text/CSV at all -- e.g. an executable or other binary file
        # renamed with a .csv extension. Never executed or passed to a
        # shell anywhere in this path; this is a clean rejection, not a
        # crash.
        print(json.dumps({"status": "invalid", "reason": "This file is not readable as CSV text -- it may be a binary/executable file, not a real DraftKings export."}))
        return

    if not dk_rows:
        print(json.dumps({"status": "invalid", "reason": "This DraftKings CSV has a valid header but zero player rows."}))
        return

    id_counts = Counter(row.dk_player_id for row in dk_rows)
    duplicate_ids = sorted(pid for pid, count in id_counts.items() if count > 1)

    missing_team = sum(1 for row in dk_rows if not row.team_abbrev)
    missing_position = sum(1 for row in dk_rows if not row.dk_positions)
    salaries = [row.salary for row in dk_rows]

    warnings = []
    if duplicate_ids:
        warnings.append(f"{len(duplicate_ids)} duplicate DraftKings player ID(s) found -- see duplicate_player_ids.")
    if missing_team:
        warnings.append(f"{missing_team} row(s) have an empty TeamAbbrev.")
    if missing_position:
        warnings.append(f"{missing_position} row(s) have no position eligibility.")

    print(json.dumps({
        "status": "valid",
        "sport": "MLB",
        "player_count": len(dk_rows),
        "salary_min": min(salaries),
        "salary_max": max(salaries),
        "teams": sorted({row.team_abbrev for row in dk_rows if row.team_abbrev}),
        "positions": sorted({p for row in dk_rows for p in row.dk_positions}),
        "duplicate_player_ids": duplicate_ids,
        "missing_team_count": missing_team,
        "missing_position_count": missing_position,
        "warnings": warnings,
    }))


if __name__ == "__main__":
    main()
