"""CLI entry point: validate and save a real DraftKings salary-export
CSV upload (Milestone 19). Unlike the tolerant CSV-projection importer
(scripts/save_projection_csv_import.py), this rejects a bad upload
immediately and loudly -- dfs/draftkings_parser.py's format checks are
precise (this is a real, structured DraftKings export, not an arbitrary
third-party CSV with a flexible column mapping step) -- so a malformed
file is never saved and never silently degrades the pipeline later.

    python scripts/upload_draftkings_csv.py --csv-path FILE --date YYYY-MM-DD \
        --slate-label Main --original-filename DKSalaries.csv
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.draftkings_parser import DraftKingsCSVFormatError, parse_salary_csv  # noqa: E402
from dfs.providers.draftkings_csv_storage import save_upload  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and save a real DraftKings salary-export CSV upload.")
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-label", required=True, help='e.g. "Main", "Turbo", "Night", "Showdown"')
    parser.add_argument("--original-filename", required=True)
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(json.dumps({"status": "error", "reason": f"CSV file not found: {csv_path}"}))
        return

    try:
        dk_rows = parse_salary_csv(csv_path)
    except DraftKingsCSVFormatError as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    if not dk_rows:
        print(json.dumps({"status": "error", "reason": "This DraftKings CSV has a valid header but zero player rows."}))
        return

    upload = save_upload(csv_path.read_bytes(), args.date, args.slate_label, args.original_filename)

    print(f"Slate label: {upload.slate_label}")
    print(f"Players: {len(dk_rows)}")
    print(f"Saved: {upload.path}")
    print(json.dumps({"status": "ready", "path": upload.path, "slate_label": upload.slate_label, "player_count": len(dk_rows)}))


if __name__ == "__main__":
    main()
