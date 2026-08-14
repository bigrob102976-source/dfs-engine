"""CLI entry point: analyze an uploaded projection CSV WITHOUT saving
anything -- powers the Import Projections wizard's Preview Mapping and
Validation Summary steps (Milestone 18). Safe to call repeatedly (e.g.
every time the user edits the column mapping).

    python scripts/analyze_projection_csv.py --csv-path FILE --provider KEY --date YYYY-MM-DD [--mapping JSON]

`--mapping` is a JSON object of canonical-field -> header-name overrides,
e.g. '{"projection": "Proj FPTS"}'. Fields omitted keep their
auto-detected mapping; a field mapped to "" or null is explicitly unmapped.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.csv_import.importer import analyze_import  # noqa: E402
from external_projections.csv_import.parser import CsvParseError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a projection CSV without saving it.")
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--date", required=True)
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
        analysis = analyze_import(csv_bytes, args.provider, args.date, manual_mapping, args.research_output_root)
    except CsvParseError as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    print(json.dumps({"status": "ok", **analysis.to_dict()}))


if __name__ == "__main__":
    main()
