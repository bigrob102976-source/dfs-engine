"""CLI entry point: delete a real DraftKings CSV upload (Milestone 19).
Refuses to delete anything outside
dfs_input/<date>/uploaded_dk_slates/ -- see
dfs/providers/draftkings_csv_storage.py::delete_upload.

    python scripts/delete_draftkings_upload.py --path FILE
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.draftkings_csv_storage import delete_upload  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete a real DraftKings CSV upload.")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    try:
        delete_upload(args.path)
    except (ValueError, OSError) as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    print(json.dumps({"status": "ok"}))


if __name__ == "__main__":
    main()
