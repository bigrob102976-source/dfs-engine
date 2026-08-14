"""CLI entry point: parse, validate, and persist an uploaded projection
CSV as an immutable External Projection baseline snapshot (Milestone
18).

    python scripts/save_projection_csv_import.py --csv-path FILE --provider KEY \
        --date YYYY-MM-DD --original-filename NAME.csv [--mapping JSON]

Refuses to save (status "no_players") when zero rows have both a name
and a projection -- an empty/all-unusable import should never produce a
snapshot. On success, the caller (the dashboard's import API route) is
expected to immediately run scripts/run_projection_adjustment.py next,
exactly as it already does for a provider-fetched baseline -- this
script does not do that itself, keeping "fetch/import a baseline" and
"run the adjustment layer" as the same two separate steps the existing
framework already uses.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.csv_import.importer import build_baseline_document  # noqa: E402
from external_projections.csv_import.parser import CsvParseError  # noqa: E402
from external_projections.persistence import save_baseline_snapshot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Save an uploaded projection CSV as an immutable baseline snapshot.")
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--original-filename", required=True)
    parser.add_argument("--mapping", default=None, help="JSON object of field -> header overrides.")
    parser.add_argument("--research-output-root", default="research_output")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(json.dumps({"status": "error", "reason": f"CSV file not found: {csv_path}"}))
        return

    manual_mapping = None
    if args.mapping:
        try:
            manual_mapping = json.loads(args.mapping)
        except json.JSONDecodeError as e:
            print(json.dumps({"status": "error", "reason": f"--mapping is not valid JSON: {e}"}))
            return

    csv_bytes = csv_path.read_bytes()

    try:
        document = build_baseline_document(
            csv_bytes, args.provider, args.date, args.original_filename, manual_mapping, args.research_output_root,
        )
    except CsvParseError as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    if document["player_count"] == 0:
        print(json.dumps({
            "status": "no_players",
            "reason": "No row in this CSV had both a name and a projection -- nothing to import.",
            "validation_summary": document["validation_summary"],
        }))
        return

    path = save_baseline_snapshot(document)

    print(f"Provider: {document['provider_name']}")
    print(f"Players imported: {document['player_count']}")
    print(f"Saved: {path}")
    print(json.dumps({
        "status": "ready",
        "path": str(path),
        "player_count": document["player_count"],
        "provider_name": document["provider_name"],
        "validation_summary": document["validation_summary"],
    }))


if __name__ == "__main__":
    main()
