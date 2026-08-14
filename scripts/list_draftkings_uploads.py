"""CLI entry point: list real DraftKings CSV uploads for one slate date
(Milestone 19's Upload DraftKings CSV history).

    python scripts/list_draftkings_uploads.py --date YYYY-MM-DD
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.draftkings_csv_storage import list_uploads  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="List real DraftKings CSV uploads for a slate date.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    uploads = list_uploads(args.date)
    uploads_sorted = sorted(uploads, key=lambda u: u.uploaded_at, reverse=True)
    print(json.dumps({"status": "ok", "slate_date": args.date, "uploads": [u.to_dict() for u in uploads_sorted]}))


if __name__ == "__main__":
    main()
