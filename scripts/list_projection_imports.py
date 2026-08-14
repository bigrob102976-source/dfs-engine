"""CLI entry point: list CSV-imported baseline snapshots for one slate
date (Milestone 18's Import History table).

    python scripts/list_projection_imports.py --date YYYY-MM-DD
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.csv_import.history import list_imports  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="List CSV-imported projection baseline snapshots for a slate date.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    imports = list_imports(args.date)
    print(json.dumps({"status": "ok", "slate_date": args.date, "imports": imports}))


if __name__ == "__main__":
    main()
