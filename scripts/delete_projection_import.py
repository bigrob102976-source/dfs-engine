"""CLI entry point: delete a CSV-imported baseline snapshot (Milestone
18's Import History "Delete" action). Refuses to delete anything outside
external_projection_snapshots/ or any snapshot not tagged
source="csv_import" -- see
external_projections/csv_import/history.py::_validate_owned_path.

    python scripts/delete_projection_import.py --path FILE
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.csv_import.history import delete_import  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete a CSV-imported baseline snapshot.")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    try:
        delete_import(args.path)
    except (ValueError, FileNotFoundError, OSError) as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    print(json.dumps({"status": "ok"}))


if __name__ == "__main__":
    main()
