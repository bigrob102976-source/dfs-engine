"""CLI entry point: make an older CSV-imported baseline snapshot active
again by writing a fresh, newer-timestamped copy of it (Milestone 18's
"Set Active Import" -- see external_projections/csv_import/history.py
for why this is a copy, never an in-place overwrite).

    python scripts/reactivate_projection_import.py --path FILE
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.csv_import.history import reactivate_import  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Reactivate a CSV-imported baseline snapshot.")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    try:
        new_path = reactivate_import(args.path)
    except (ValueError, FileNotFoundError, OSError) as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    print(json.dumps({"status": "ready", "path": new_path}))


if __name__ == "__main__":
    main()
